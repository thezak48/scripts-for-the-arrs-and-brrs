#!/usr/bin/env python
# -*- coding: utf-8 -*-

# based on this: https://github.com/blacktwin/JBOPS

"""
Find what was added TFRAME ago and not watched using Tautulli.
"""
from __future__ import print_function
from __future__ import unicode_literals

from builtins import str
from builtins import object
import requests
import sys
import time
import os
import csv

TFRAME = 1.577e7  # ~ 6 months in seconds
TODAY = time.time()

# ## EDIT THESE SETTINGS ##
TAUTULLI_APIKEY = "api_key"  # Your Tautulli API key
TAUTULLI_URL = "http://localhost:8181/tautulli"  # Your Tautulli URL
LIBRARY_NAMES = ["TV Shows", "Movies"]  # Name of libraries you want to check.

# CSV file names
MOVIES_CSV = "unwatched_movies.csv"
SHOWS_CSV = "unwatched_shows.csv"


class LIBINFO(object):
    def __init__(self, data=None):
        d = data or {}
        self.added_at = d["added_at"]
        self.parent_rating_key = d["parent_rating_key"]
        self.play_count = d["play_count"]
        self.title = d["title"]
        self.rating_key = d["rating_key"]
        self.media_type = d["media_type"]


class METAINFO(object):
    def __init__(self, data=None):
        d = data or {}
        self.added_at = d["added_at"]
        self.parent_rating_key = d["parent_rating_key"]
        self.title = d["title"]
        self.rating_key = d["rating_key"]
        self.media_type = d["media_type"]
        self.grandparent_title = d["grandparent_title"]
        media_info = d["media_info"][0]
        parts = media_info["parts"][0]
        self.file_size = parts["file_size"]
        self.file = parts["file"]


def get_new_rating_keys(rating_key, media_type):
    # Get a list of new rating keys for the PMS of all of the item's parent/children.
    payload = {
        "apikey": TAUTULLI_APIKEY,
        "cmd": "get_new_rating_keys",
        "rating_key": rating_key,
        "media_type": media_type,
    }

    try:
        r = requests.get(TAUTULLI_URL.rstrip("/") + "/api/v2", params=payload)
        response = r.json()

        res_data = response["response"]["data"]
        show = res_data["0"]
        episode_lst = [
            episode["rating_key"]
            for _, season in show["children"].items()
            for _, episode in season["children"].items()
        ]

        return episode_lst

    except Exception as e:
        sys.stderr.write(
            "Tautulli API 'get_new_rating_keys' request failed: {0}.".format(e)
        )


def get_metadata(rating_key):
    # Get the metadata for a media item.
    payload = {
        "apikey": TAUTULLI_APIKEY,
        "rating_key": rating_key,
        "cmd": "get_metadata",
        "media_info": True,
    }

    try:
        r = requests.get(TAUTULLI_URL.rstrip("/") + "/api/v2", params=payload)
        response = r.json()

        res_data = response["response"]["data"]
        return METAINFO(data=res_data)

    except Exception:
        # sys.stderr.write("Tautulli API 'get_metadata' request failed: {0}.".format(e))
        pass


def get_library_media_info(section_id):
    # Get the data on the Tautulli media info tables.
    payload = {
        "apikey": TAUTULLI_APIKEY,
        "section_id": section_id,
        "cmd": "get_library_media_info",
        "length": 10000,
    }

    try:
        r = requests.get(TAUTULLI_URL.rstrip("/") + "/api/v2", params=payload)
        response = r.json()

        res_data = response["response"]["data"]["data"]
        return [
            LIBINFO(data=d)
            for d in res_data
            if d["play_count"] is None and (TODAY - int(d["added_at"])) > TFRAME
        ]

    except Exception as e:
        sys.stderr.write(
            "Tautulli API 'get_library_media_info' request failed: {0}.".format(e)
        )


def get_libraries_table():
    # Get the data on the Tautulli libraries table.
    payload = {"apikey": TAUTULLI_APIKEY, "cmd": "get_libraries_table"}

    try:
        r = requests.get(TAUTULLI_URL.rstrip("/") + "/api/v2", params=payload)
        response = r.json()

        res_data = response["response"]["data"]["data"]
        return [d["section_id"] for d in res_data if d["section_name"] in LIBRARY_NAMES]

    except Exception as e:
        sys.stderr.write(
            "Tautulli API 'get_libraries_table' request failed: {0}.".format(e)
        )


def save_to_csv(file_name, rows):
    with open(file_name, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Title", "Rating Key", "Date Added", "File Location"])
        writer.writerows(rows)


show_lst = []
path_lst = []
movies_data = []
shows_data = []

glt = [lib for lib in get_libraries_table()]

for i in glt:
    try:
        gglm = get_library_media_info(i)
        for x in gglm:
            try:
                if x.media_type in ["show", "episode"]:
                    # Need to find TV shows rating_key for episode.
                    show_lst += get_new_rating_keys(x.rating_key, x.media_type)
                else:
                    # Find movie rating_key.
                    show_lst += [int(x.rating_key)]
            except Exception as e:
                print(("Rating_key failed: {e}").format(e=e))

    except Exception as e:
        print(("Library media info failed: {e}").format(e=e))

# Remove reverse sort if you want the oldest keys first.
for i in sorted(show_lst, reverse=True):
    try:
        x = get_metadata(str(i))
        added = time.ctime(float(x.added_at))
        if x.grandparent_title == "" or x.media_type == "movie":
            # Movies
            print(
                "{x.title} ({x.rating_key}) was added {when} and has not been "
                "watched. \n File location: {x.file}".format(x=x, when=added)
            )
            movies_data.append([x.title, x.rating_key, added, x.file])
        else:
            # Shows
            print(
                "{x.grandparent_title}: {x.title} ({x.rating_key}) was added {when} and has "
                "not been watched. \n File location: {x.file}".format(x=x, when=added)
            )
            shows_data.append(
                [x.grandparent_title + ": " + x.title, x.rating_key, added, x.file]
            )
        path_lst += [x.file]

    except Exception as e:
        print(("Metadata failed. Likely end of range: {e}").format(e=e))

# Save the data to CSV files
save_to_csv(MOVIES_CSV, movies_data)
save_to_csv(SHOWS_CSV, shows_data)

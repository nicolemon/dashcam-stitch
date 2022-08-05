#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
import pathlib
import tempfile
import logging
import argparse
from celery import Celery, group
from celery.utils.log import get_task_logger


redis_pass = os.getenv('REDIS_PASS')

app = Celery('stitch', broker=f"redis://:{redis_pass}@localhost:6379/2")
app.config_from_object('stitcher_config')
app.autodiscover_tasks()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# logger formatting
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')

# file handler
file_handler = logging.FileHandler(filename='logfile')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.DEBUG)

# stream handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.INFO)

# add handlers
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

FILENAME_PATTERN = re.compile(r"(?P<date>\d{4}_\d{4}_\d{6})_(?P<part>\d+)(?P<type>(F|PF))")


def directory_video_sets(directory):
    """Feeds video files from a directory into the FIXME blahblah"""
    working_dir = pathlib.Path(directory)

    if not working_dir.is_dir():
        raise ValueError('Directory not found: %s', working_dir)

    video_list = sorted(working_dir.glob('*.MP4'))

    return _generate_video_sets(video_list)


def filename_video_sets(textfile):
    """FIXME Parses a text file of video paths to stitch together"""
    working_file = pathlib.Path(textfile)

    if not working_file.is_file():
        raise ValueError('File not found: %s', working_file)

    with open(working_file, mode='r', encoding='utf-8') as fp:
        _file_contents = fp.readlines()

    video_list = [f.strip('\n') for f in _file_contents if f.strip('\n').endswith('.MP4')]

    return _generate_video_sets(video_list)


def _generate_video_sets(video_list):
    """Partitions the video files by parking mode

    Creates a mapping of the start timestamp to the list of video files to
    stitch together
    """
    video_sets = {}

    # seed search identifiers
    parked = None
    video_start = None
    video_parts = []

    for _video_name in video_list:
        video_name = str(_video_name)
        if isinstance(_video_name, pathlib.Path):
            _video_data = FILENAME_PATTERN.match(_video_name.stem)
        else:
            _video_data = FILENAME_PATTERN.match(_video_name)

        timestamp = _video_data.group('date')
        part = _video_data.group('part')
        if _video_data.group('type') == "PF":
            _parked = True
        elif _video_data.group('type') == "F":
            _parked = False
        else:  # this should never be reached
            raise ValueError('Unable to parse file name: %s', _video_name)

        if _parked == parked:
            video_parts.append(video_name)
        else:
            if video_start is not None:
                video_sets[video_start] = video_parts

            video_parts = [video_name]
            parked = _parked
            video_start = timestamp
            if _parked:
                video_start += '_parked'

    return video_sets


@app.task(name='stitch')
def _stitch_videos(file_list, output_file):
    """Stitching task

    This computer has about 12 more cores than I need so I might as well use it
    for something and run these jobs asynchronously!
    """
    import ffmpeg

    inputs = [ffmpeg.input(file) for file in file_list]
    (
        ffmpeg
        .concat(*inputs)
        .output(output_file)
        .overwrite_output()
        .run(capture_stdout=True)
    )

    return str(output_file)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Stitch together VIOFO A129 dashcam footage partitioned by parking mode')
    parser.add_argument('input_path', action='store', help='Path to directory of dashcam videos')
    parser.add_argument('output_directory', action='store', help='Name of output directory of stitched videos')
    parser.add_argument('-d', '--output-path', action='store', default=None, help='Path to parent of output directory (default: ~/videos)')
    parser.add_argument('-C', '--check-mode', action='store_true', help='Check mode')

    args = parser.parse_args()

    video_datas = directory_video_sets(args.input_path)

    if not args.output_path:
        outdir = pathlib.Path.home().joinpath('videos', args.output_directory)
    else:
        outdir = pathlib.Path(args.output_path).joinpath(args.output_directory)

    outdir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for filename, file_list in video_datas.items():
        outfile = outdir.joinpath(f"{filename}.mp4")

        if not args.check_mode:
            task = _stitch_videos.s(file_list, str(outfile))
            tasks.append(task)

        logger.info(outfile)
        for file in file_list:
            logger.info(' * %s', file)

    if not args.check_mode:
        stitch_job = group(tasks)()
        stitch_job.save()
        logger.info('Stitch Job ID: %s', stitch_job.id)

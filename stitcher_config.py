#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os


redis_pass = os.getenv('REDIS_PASS')

broker_url = f"redis://:{redis_pass}@localhost:6379/2"
result_backend = f"redis://:{redis_pass}@localhost:6379/2"
task_serializer = 'json'
result_serializer = 'json'
timezone = 'US/Pacific'
task_routes = {
    'stitch': 'stitcher',
    'sync': 'syncer'
}

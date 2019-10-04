#!/usr/bin/python3

from libhikvision import libHikvision
from datetime import datetime

cameradir = '/home/bkbilly/Desktop/hikvision/'
hik = libHikvision(cameradir, 'video')
segments = hik.getSegments(
    from_time=datetime(2019, 8, 21, 22, 23, 30),
    to_time=datetime(2019, 8, 21, 22, 25, 00),
)

for num, segment in enumerate(segments, start=0):
    print('{0:4}) {1[cust_filePath]:55} {1[cust_duration]:5} {1[startOffset]:10} {1[endOffset]:10}   {1[cust_startTime]} - {1[cust_endTime]}'.format(
        num,
        segment
    ))

# hik.extractSegmentJPG(2, '/home/bkbilly/Desktop/')
# for file in hik.getFiles():
#     print(file)

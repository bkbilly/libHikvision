# LibHikvision
[![PyPI Version](https://img.shields.io/pypi/v/libHikvision?label=PyPI&logo=pypi)](https://pypi.org/project/libHikvision/)


Python library to parse Hikvision datadirs that Hikvision IP cameras store the videos.
Using this class you can view details about recordings stored in a datadir and extract video and thumbnails.


### Working Example

```python
#!/usr/bin/python3

from libhikvision import libHikvision
from datetime import datetime
from datetime import timedelta

cameradir = '/var/tmp/hikvision/'
hik = libHikvision(cameradir, 'video')

# Get information about the server
print(hik.getNASInfo())

# Extract the segments within a specific range of dates
# segments = hik.getSegments(
#    from_time=datetime(2023, 5, 5, 8, 0, 0),
#    to_time=datetime(2023, 5, 20, 23, 59, 00),
#)

# Extract last 3 Hours
segments = hik.getSegments(
    from_time=(datetime.now() - timedelta(hours=3)),
    to_time=(datetime.now()),
)

# Extract the Videos and Images from segments found above
for num, segment in enumerate(segments, start=0):
    print('{0:4}) {1[cust_filePath]:55} {1[cust_duration]:5} {1[startOffset]:10} {1[endOffset]:10}   {1[cust_startTime]} - {1[cust_endTime]}'.format(
        num,
        segment
    ))
    oDate = datetime.strptime("{0[cust_startTime]}".format(segment), '%Y-%m-%d %H:%M:%S')
    sDateFormated=oDate.strftime('%Y%m%d-%H%M%S')
    print(hik.extractSegmentMP4(num, cachePath='/var/tmp/', filename='/var/tmp/video-{0}.mp4'.format(sDateFormated)))
    print(hik.extractSegmentJPG(num, cachePath='/var/tmp/', filename='/var/tmp/video-{0}.jpg'.format(sDateFormated)))
```

You should also check the documentation of each method for extra options.

### Credits

Based on Dave Hope's PHP code available at https://github.com/davehope/libHikvision



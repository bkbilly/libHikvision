# LibHikvision
[![PyPI Version](https://img.shields.io/pypi/v/libHikvision?label=PyPI&logo=pypi)](https://pypi.org/project/libHikvision/)


Python library to parse Hikvision datadirs that Hikvision IP cameras and DVRs store the videos.
Using this class you can view details about recordings stored in a datadir and extract video and thumbnails.


### Working Example

```python
#!/usr/bin/python3

from libhikvision import libHikvision
from datetime import datetime
from datetime import timedelta

cameradir = '/var/tmp/hikvision/' # Can be a directory path or direct path to an index file (.bin)
hik = libHikvision(cameradir, 'video')

# Get information about the server
print(hik.getNASInfo())

# Extract the segments within a specific range of dates (and optionally filter by channel for DVRs)
# segments = hik.getSegments(
#    from_time=datetime(2023, 5, 5, 8, 0, 0),
#    to_time=datetime(2023, 5, 20, 23, 59, 00),
#    channel=8,
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

### CLI Usage

`libHikvision` provides a command-line interface to inspect archives and extract videos/thumbnails directly from the terminal.

```bash
# List all segments in a directory or direct .bin file
libhikvision /path/to/cameradir
libhikvision /path/to/cameradir/INDEX00.bin

# Filter by channel and time range
libhikvision /path/to/cameradir -c 8 --from "2026-07-16 18:00:00" --to "2026-07-16 22:00:00"

# Print storage and header information (supports --json for scripting)
libhikvision /path/to/cameradir --info --header --json

# Extract specific segments to MP4 / JPG
libhikvision /path/to/cameradir -c 8 --extract-mp4 0,1,2 -o ./output/
libhikvision /path/to/cameradir -c 8 --extract-mp4 all -o ./output/
libhikvision /path/to/cameradir -c 8 --extract-jpg 0 -o ./output/
```

### Credits

Based on Dave Hope's PHP code available at https://github.com/davehope/libHikvision

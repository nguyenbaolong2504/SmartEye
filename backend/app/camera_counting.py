"""Count each confirmed ByteTrack identity once, with replay-safe frame totals."""
from collections import Counter
from types import SimpleNamespace
import numpy as np

VERSION=1
LABELS=('car','motorcycle','bus','truck')


def cumulative_tracks(frames,fps):
    from ultralytics.engine.results import Boxes
    from ultralytics.trackers.byte_tracker import BYTETracker
    tracker=BYTETracker(SimpleNamespace(track_high_thresh=.25,track_low_thresh=.1,
        new_track_thresh=.25,track_buffer=max(15,round(fps*2)),match_thresh=.8,fuse_score=True))
    seen={};totals=Counter();output=[]
    for frame in frames:
        boxes=frame['boxes']
        raw=np.asarray([[*box['box'],box['confidence'],LABELS.index(box['label'])] for box in boxes],dtype=np.float32).reshape(-1,6)
        tracked=tracker.update(Boxes(raw,(frame['height'],frame['width'])))
        identities={int(row[-1]):int(row[4]) for row in tracked}
        annotated=[]
        for index,box in enumerate(boxes):
            ident=identities.get(index)
            if ident is not None and ident not in seen:
                seen[ident]=box['label'];totals[box['label']]+=1
            # Freeze a counted track's category, so a later class flicker cannot
            # move an already-counted vehicle between cumulative categories.
            annotated.append({**box,'track_id':ident,'counted_as':seen.get(ident)})
        counts={label:totals[label] for label in LABELS}
        output.append({**frame,'boxes':annotated,'cumulative_count':sum(counts.values()),
            'cumulative_vehicle_counts':counts,'tracked_count':len(identities)})
    return output

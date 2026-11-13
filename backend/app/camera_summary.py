"""Summarize the end of one complete recording without adding repeated vehicles."""
from collections import Counter
from statistics import median


def summarize_video(result):
    frames=result.get('frames') or result.get('samples') or []
    if not frames:raise ValueError('Video chưa có dữ liệu nhận diện để phân tích.')
    fps=result.get('fps') or result.get('sample_rate') or 1
    end=frames[-1]['second']+1/fps
    start=max(0.,end-10.)
    window=[row for row in frames if start<=row['second']<end]
    score=float(median(row['score'] for row in window))
    # This real frame is shown in the explanation. Model inputs use temporal
    # summaries; neither a final cumulative ID total nor a single peak replaces them.
    basis=min(window,key=lambda row:(abs(row['score']-score),-row['second']))
    sample={**basis,'second':frames[-1]['second'],'score':score,
            'count':round(median(row['count'] for row in window))}
    loads=[row['load_ratio'] for row in window if row.get('load_ratio') is not None]
    if loads:sample['load_ratio']=float(median(loads))
    movement=[row for row in window if row.get('motion_known') and row.get('stopped_share') is not None]
    sample['motion_known']=len(movement)>=max(1,len(window)*.3)
    sample['stopped_share']=sum(row['stopped_share'] for row in movement)/len(movement) if sample['motion_known'] else None
    keys=('second','frame_index','count','score','occupancy','density','vehicle_counts','equivalent_count',
          'capacity_pcu','load_ratio','motion_known','stopped_share','cumulative_count','cumulative_vehicle_counts')
    evidence={key:basis[key] for key in keys if key in basis}
    if 'vehicle_counts' not in evidence:
        counts=Counter(box['label'] for box in basis.get('boxes',[]))
        evidence['vehicle_counts']={key:counts[key] for key in ('car','motorcycle','bus','truck')}
        evidence['vehicle_counts']['motorcycle']+=counts['motorbike']
    return sample,evidence,{'start_second':round(start,3),'end_second':round(end,3),
        'observed_seconds':round(end-start,3),'frames':len(window),'median_count':float(median(row['count'] for row in window)),
        'median_score':score,'median_load_ratio':sample.get('load_ratio'),'motion_known':sample['motion_known'],
        'stopped_share':sample['stopped_share'],'representative_second':basis['second']}

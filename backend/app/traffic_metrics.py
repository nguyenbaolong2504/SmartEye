"""Traffic quantities with explicit units. Unknown measurements stay unknown.

q counts crossings, k counts vehicles present. CI is this project's speed-loss
index, not a probability. Storage PCU and image occupancy are neither q nor k.
"""
import math

VERSION = 1


def number(value, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= minimum and (maximum is None or value <= maximum) else None


def quantities(*, present_count=None, length_m=None, lanes=None, crossings=None,
               observed_seconds=None, speed_kmh=None, free_flow_speed_kmh=None,
               distance_km=None, length_verified=False, speed_verified=False):
    n = number(present_count); length = number(length_m, .001)
    count = number(crossings); seconds = number(observed_seconds, .001)
    speed = number(speed_kmh, 0, 200) if speed_verified else None
    free = number(free_flow_speed_kmh, .001, 200)
    lane_count = number(lanes, 1, 12)
    density = n / (length / 1000) if n is not None and length and length_verified else None
    flow = count * 3600 / seconds if count is not None and seconds else None
    ci = min(1., max(0., 1 - speed / free)) if speed is not None and free else None
    # At standstill travel time is unbounded; do not divide by zero or invent ETA.
    tti = free / speed if free and speed is not None and speed > 0 else None
    distance = number(distance_km, .000001)
    eta = distance / speed * 60 if distance and speed is not None and speed > 0 else None
    band = None if ci is None else ('FREE' if ci < .25 else 'SLOW' if ci < .5 else 'DENSE' if ci < .7 else 'SEVERE')
    return {'version': VERSION,'present_count':n,'observed_length_m':length,'lanes':lane_count,'flow_veh_per_hour': flow,
            'flow_veh_per_hour_per_lane': flow / lane_count if flow is not None and lane_count else None,
            'density_veh_per_km': density,
            'density_veh_per_km_per_lane': density / lane_count if density is not None and lane_count else None,
            'avg_speed_kmh': speed, 'free_flow_speed_kmh': free, 'congestion_index': ci,
            'speed_loss_band': band, 'travel_time_index': tti, 'travel_minutes': eta,
            'standstill': speed == 0 if speed is not None else None,
            'quality': {'length_verified': bool(length_verified and length),
                        'speed_calibrated': bool(speed_verified and speed is not None),
                        'flow_count_method': 'line_crossings' if flow is not None else 'unknown'}}


FORMULAS = {
    'flow_veh_per_hour': 'N_crossings / observed_seconds × 3600',
    'density_veh_per_km': 'N_present / (observed_length_m / 1000)',
    'speed_kmh': '3.6 × sum(distance_m) / sum(travel_seconds)',
    'congestion_index': 'clip(1 - avg_speed_kmh / free_flow_speed_kmh, 0, 1)',
    'travel_time_index': 'free_flow_speed_kmh / avg_speed_kmh',
    'travel_minutes': 'distance_km / avg_speed_kmh × 60',
    'historical_jam_frequency': 'jam_days / valid_comparable_days',
}

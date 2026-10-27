"""Generate a non-personal empty-scene fixture for the upload E2E workflow."""
from pathlib import Path
import argparse
import cv2
import numpy as np

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--format',choices=['avi','webm'],default='avi')
    args=parser.parse_args()
    target=Path(__file__).resolve().parents[1]/f'backend/data/e2e-empty-road.{args.format}'
    target.parent.mkdir(parents=True,exist_ok=True)
    image=np.full((360,640,3),80,np.uint8)
    cv2.line(image,(250,360),(300,0),(190,190,190),3)
    cv2.line(image,(390,360),(340,0),(190,190,190),3)
    writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*('VP80' if args.format=='webm' else 'MJPG')),10,(640,360))
    if not writer.isOpened(): raise RuntimeError('Cannot encode E2E fixture')
    for _ in range(20): writer.write(image)
    writer.release()
    print('E2E video fixture ready')

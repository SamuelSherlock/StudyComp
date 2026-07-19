import cv2
import json
from ultralytics import YOLO
import time

MAX_ABSENCE_SECONDS = 10  # maximum time allowed without detecting a person before flagging as absent

class Detector:

    def __init__(self):
        self.activated = False

    def activate_camera(self):
        model = YOLO('yolov8l.pt')  # loads pretrained model
        cap = None
        for index in range(3):   # try camera indexes 0, 1, 2
            candidate = cv2.VideoCapture(index)
            if candidate.isOpened():
                cap = candidate
                break

        if cap is None:
            print("Could not find any working camera.")
            return 
        
        phone_class_id = None
        remote_class_id = None
        person_class_id = None
        frames = 0
        consecutive_frames = 0
        detection_threshold = 5
        self.activated = True
        present_last_frame = True
        person_last_seen = time.time()  # initialize the last seen time for person detection
        absence_reported = False  # flag to track if absence has been reported
        for i, name in model.names.items():  # loop through each object and its index to find cellphone index
            if name == "cell phone":
                phone_class_id = i
            elif name == "remote":
                remote_class_id = i
            elif name == "person":
                person_class_id = i

        while self.activated:
            ret, frame = cap.read()
            if not ret:
                break

            frames += 1
            results = model(frame, verbose=False)[0]
            # x1 y1 is top left corner
            # x2 y2 is bottom right corner

            phone_detected_this_frame = False
            person_detected_this_frame = False

            for box in results.boxes:  # runs everytime object detected
                object_id = int(box.cls[0])  # extract objects class id
                confidence = float(box.conf[0])  # extract confidence score

                x1, y1, x2, y2 = box.xyxy[0]

                object_area = (x2 - x1) * (y2 - y1)  # width times height
                frame_area = frame.shape[0] * frame.shape[1]
                # frame.shape0 is height, 1 is width

                object_ratio = object_area / frame_area  # object area divided by frame area

                if (object_id == phone_class_id or object_id == remote_class_id) and (confidence > 0.5 and object_ratio > 0.05):
                    phone_detected_this_frame = True
                if object_id == person_class_id and (confidence > 0.5 and object_ratio > 0.1):
                    person_detected_this_frame = True


            if phone_detected_this_frame:
                consecutive_frames += 1
            else:
                consecutive_frames = 0

          
            if person_detected_this_frame:
                if absence_reported:   # they just came back, after we'd already flagged them absent
                    print(json.dumps({"status": "person_detected"}), flush=True)
                    absence_reported = False
                person_last_seen = time.time()
            else:
             if not absence_reported and (time.time() - person_last_seen > MAX_ABSENCE_SECONDS):
                try:
                    print(json.dumps({"status": "no_person"}), flush=True)
                    absence_reported = True
                except BrokenPipeError:
                    break   # listener's gone, no point continuing
                             
               
            
        cap.release()

    def deactivate_camera(self):
        self.activated = False

if __name__ == "__main__":
    detector = Detector()
    detector.activate_camera()
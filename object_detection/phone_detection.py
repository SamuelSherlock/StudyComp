import cv2
from ultralytics import YOLO

class Detector:

    def __init__(self):
        self.activated = False

    def activate_camera(self):
        model = YOLO('yolov8l.pt')  # loads pretrained model
        cap = cv2.VideoCapture(0)
        phone_class_id = None
        remote_class_id = None
        frames = 0
        consecutive_frames = 0
        detection_threshold = 5
        self.activated = True

        for i, name in model.names.items():  # loop through each object and its index to find cellphone index
            if name == "cell phone":
                phone_class_id = i
            elif name == "remote":
                remote_class_id = i

        while self.activated:
            ret, frame = cap.read()
            if not ret:
                break

            frames += 1
            results = model(frame, verbose=False)[0]
            # x1 y1 is top left corner
            # x2 y2 is bottom right corner

            phone_detected_this_frame = False

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

            if phone_detected_this_frame:
                consecutive_frames += 1
            else:
                consecutive_frames = 0

            if consecutive_frames >= detection_threshold:  # if cellphone detected for 5 consecutive frames
                print("return to studying")  # print message
                consecutive_frames = 0  # reset counter

        cap.release()

    def deactivate_camera(self):
        self.activated = False
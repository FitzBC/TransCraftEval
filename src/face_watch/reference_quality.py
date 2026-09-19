"""Conservative reference-image checks, not an identity or recognition guarantee.

Thresholds are initial screening heuristics; score the face region, never the
busy background. Pose is a landmark asymmetry warning, not calibrated yaw.
"""
import cv2
import numpy as np


def assess_reference(image, faces):
    reasons=[]
    metrics={'face_count':len(faces)}
    if len(faces)!=1:
        return {'version':'reference-quality-v1','issues':['需要清晰的单人照片'],'metrics':metrics}
    face=np.asarray(faces[0],dtype=float)
    x,y,w,h=face[:4]
    metrics['face_short_side']=round(float(min(w,h)),1)
    if min(w,h)<80:
        reasons.append('脸部太小，请换近景照片')
    height,width=image.shape[:2]
    crop=image[max(0,int(y)):min(height,int(y+h)),max(0,int(x)):min(width,int(x+w))]
    if crop.size==0:
        reasons.append('脸部区域不完整')
    else:
        gray=cv2.cvtColor(cv2.resize(crop,(112,112),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2GRAY)
        sharpness=float(cv2.Laplacian(gray,cv2.CV_64F).var())
        metrics['face_sharpness']=round(sharpness,2)
        if sharpness<25:
            reasons.append('脸部细节偏模糊，请换清晰原图')
    if x<0 or y<0 or x+w>width or y+h>height:
        reasons.append('脸部超出画面边缘')
    if len(face)>=14:
        eye_a,eye_b,nose=face[4:6],face[6:8],face[8:10]
        eye_distance=float(np.linalg.norm(eye_b-eye_a))
        if eye_distance>1:
            asymmetry=abs(float(np.dot(nose-(eye_a+eye_b)/2,(eye_b-eye_a)/eye_distance)))/eye_distance
            metrics['pose_asymmetry']=round(asymmetry,3)
            if asymmetry>.45:
                reasons.append('面部角度可能偏侧，请优先使用正面照片')
    return {'version':'reference-quality-v1','issues':reasons,'metrics':metrics}

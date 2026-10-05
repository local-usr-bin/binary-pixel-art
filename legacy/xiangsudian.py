import os
import cv2
import numpy as np
import sys
import getopt
from PIL import Image

def usage():
    print(
"""
Usage: python3 xiantu.py [-h][-d][-s][-i][-o][-c][-t][-b]
-h:show the help information
-d:horizontal pixels of the output image, default 1000
-s:size of the dot (length of pixels), defult 2 
-t:therod for gray, 0-255,default 127
-b:therod for black,0-255,defualt 60
-c:autoscale(color), y: yes, n: no, default y
example: python3 ./xiantu.py -d 3000 --i ./test.jpg -o ./result.jpg
"""
    )

input_file = 'q'
output_file = 'q'
d = 1000
s = 2
c = 'y'
t = 127
b = 60


opts, args = getopt.getopt(sys.argv[1:], '-h-d:-s:-i:-o:-c:-t:-b:')  

for cmd, arg in opts:
    if cmd == '-h':
        print("help info")
        usage()
        sys.exit()
    elif cmd == '-d':
        d = int(arg)
    elif cmd == '-s':
        s = int(arg)
    elif cmd == '-t':
        t = int(arg)
    elif cmd == '-t':
        t = int(arg)
    elif cmd == '-i':
        input_file = arg
    elif cmd =='-o':
        output_file = arg
    elif cmd == '-c':
        c = arg

if input_file == 'q':
    usage()
    sys.exit()
if output_file == 'q':
    usage()
    sys.exit()

img_input = cv2.imread(input_file,cv2.IMREAD_UNCHANGED)

if c == 'y':
    img_s =  cv2.imread(input_file,0)
    img_s_e = cv2.equalizeHist(img_s)
    img_input = cv2.cvtColor(img_s_e,cv2.COLOR_GRAY2BGR)

img = cv2.resize(img_input,(d,int(d*img_input.shape[0]/img_input.shape[1])))
img_d = cv2.resize(img,(int(img.shape[1]/s),int(int(img.shape[0]/s))))
img_r_d = np.zeros((img_d.shape[0],img_d.shape[1],3), np.uint8)
img_r_d[:] = [255,255,255]
    
for i in range(0,img_d.shape[0],2):
    for j in range(0,img_d.shape[1],2):     
        a = (int(img_d[i,j][0]) + int(img_d[i,j][1]) +int(img_d[i,j][2]))/3
        if a < t:     
            img_r_d[i,j][0] = 0
            img_r_d[i,j][1] = 0
            img_r_d[i,j][2] = 0

for i in range(0,img_d.shape[0]):
    for j in range(0,img_d.shape[1]):     
        a = (int(img_d[i,j][0]) + int(img_d[i,j][1]) +int(img_d[i,j][2]))/3
        if a < b:     
            img_r_d[i,j][0] = 0
            img_r_d[i,j][1] = 0
            img_r_d[i,j][2] = 0

img_r = cv2.resize(img_r_d,(d,int(d*img_input.shape[0]/img_input.shape[1])),interpolation=cv2.INTER_NEAREST)
              
cv2.imwrite(output_file,img_r)
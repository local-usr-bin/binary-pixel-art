import os
import cv2
import numpy as np
import sys
import getopt
from PIL import Image

def usage():
    print(
"""
Usage: python3 xiantu.py [-h][-s][-t][-i][-o]
-h:show the help information
-s:size of the dot (length of pixels), defult 30
-t: default 0, add color to white dots, value 0-1
-i:input file
-o:output file
example: python3 ./xiantu.py -s30 -i ./test.jpg -o ./result.jpg
"""
    )

input_file = 'q'
output_file = 'q'
d = 1000
s = 30
t = 0


opts, args = getopt.getopt(sys.argv[1:], '-h-s:-i:-o:-t:')  

for cmd, arg in opts:
    if cmd == '-h':
        print("help info")
        usage()
        sys.exit()
    elif cmd == '-s':
        s = int(arg)
    elif cmd == '-t':
        t = float(arg)
    elif cmd == '-i':
        input_file = arg
    elif cmd =='-o':
        output_file = arg


if input_file == 'q':
    usage()
    sys.exit()
if output_file == 'q':
    usage()
    sys.exit()

img_input = cv2.imread(input_file,cv2.IMREAD_UNCHANGED) #打开原图像RGB

img_s= np.zeros((int(img_input.shape[0]/s),int(img_input.shape[1]/s),3),np.uint8) #建立低分辨率图像

for i in range(0,img_s.shape[0]):
    for j in range(0,img_s.shape[1]):
        img_s[i,j][0] = 0
        img_s[i,j][1] = 0
        img_s[i,j][2] = 0   #小图所有像素填充黑色

for i in range(0,img_s.shape[0],2):
    for j in range(0,img_s.shape[1],2):
        img_s[i,j][0] = 255
        img_s[i,j][1] = 255
        img_s[i,j][2] = 255    #小图间隔填充白色

img_l = cv2.resize(img_s,(img_input.shape[1],img_input.shape[0]),interpolation=cv2.INTER_NEAREST) #临近差值放大小图至与原图相同分辨率

for i in range(0,img_input.shape[0]):
    for j in range(0,img_input.shape[1]):  #遍历原图所有像素
        if img_l[i,j][0] == 0:  
            continue                   #img_l中黑色像素对应的原图像素不做处理
        else:                          #img_l中白色像素对应的原图像素修改颜色
            a = 255 - ( t* (255-img_input[i,j][0]) )
            b = 255 - ( t* (255-img_input[i,j][1]) )
            c = 255 - ( t* (255-img_input[i,j][2]) )
            img_input[i,j][0] = a
            img_input[i,j][1] = b
            img_input[i,j][2] = c  

cv2.imwrite(output_file,img_input) #保存图像


        

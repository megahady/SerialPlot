import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore
from numpy import *
import serial
import time
import threading, multiprocessing

read_data = []
cnt =0
ser_bytes=[]
id_number = []
pkt_cnt=[]
totalpacket=0

windowWidth= 100
app = pg.mkQApp()
mw = QtGui.QMainWindow()
mw.resize(1000,250)
cw = QtGui.QWidget()
mw.setCentralWidget(cw)
l = QtGui.QVBoxLayout()
cw.setLayout(l)

pw1 = pg.PlotWidget(name='Plot1')  ## giving the plots names allows us to link their axes together
curve1 = pw1.plot(clear=True,pen={'color':'m', 'cosmetic':False, 'width': 2})
l.addWidget(pw1)
Val1 = linspace(0,0,windowWidth)          # create array that will contain the relevant time series
ptr1 = -windowWidth                      # set first x position

pw2 = pg.PlotWidget(name='Plot2')  ## giving the plots names allows us to link their axes together
curve2 = pw2.plot(clear=True,pen={'color':'m', 'cosmetic':False, 'width': 2})
l.addWidget(pw2)
Val2 = linspace(0,0,windowWidth)          # create array that will contain the relevant time series
ptr2 = -windowWidth                      # set first x position

pw3 = pg.PlotWidget(name='Plot3')  ## giving the plots names allows us to link their axes together
curve3 = pw3.plot(clear=True,pen={'color':'m', 'cosmetic':False, 'width': 2})
l.addWidget(pw3)
Val3 = linspace(0,0,windowWidth)          # create array that will contain the relevant time series
ptr3 = -windowWidth                      # set first x position
#
pw4 = pg.PlotWidget(name='Plot4')  ## giving the plots names allows us to link their axes together
curve4 = pw4.plot(clear=True,pen={'color':'m', 'cosmetic':False, 'width': 2})
l.addWidget(pw4)
Val4 = linspace(0,0,windowWidth)          # create array that will contain the relevant time series
ptr4 = -windowWidth                      # set first x position
#
pw5 = pg.PlotWidget(name='Plot5')  ## giving the plots names allows us to link their axes together
curve5 = pw5.plot(clear=True,pen={'color':'m', 'cosmetic':False, 'width': 2})
l.addWidget(pw5)
Val5 = linspace(0,0,windowWidth)          # create array that will contain the relevant time series
ptr5 = -windowWidth                      # set first x position

pw6 = pg.PlotWidget(name='Plot6')  ## giving the plots names allows us to link their axes together
curve6 = pw6.plot(clear=True,pen={'color':'m', 'cosmetic':False, 'width': 2})
l.addWidget(pw6)
Val6 = linspace(0,0,windowWidth)          # create array that will contain the relevant time series
ptr6 = -windowWidth                      # set first x position

mw.show()

def UpdateGraphnode(queuenodeBytes,Val,curve,ptr):
    global ptr1, Val1, curve1
    if not queuenodeBytes.empty():
        valueofgraph = queuenodeBytes.get(timeout=5)
        # print("node1", valueofgraph)
        Val[:-1] = Val[1:]
        Val[-1] = valueofgraph
        curve.setData(Val)
        curve.setPos(ptr,0)
        ptr+=1
        curve.setPen('w')

def ReadBytenode(queueArraynode,queuenodeBytes):
    index = 0
    if not queueArraynode.empty():
        arrbytes = queueArraynode.get(timeout=5)
        # print("len",len(arrbytes))
        while index < 244:
                byteofarr = float(arrbytes[index])
                queuenodeBytes.put(byteofarr)
                # print("byteofarr",byteofarr)
                index =index + 1


def ReadFunction(queue):
    global ser_bytes, id_number, pkt_cnt,ser_bytes_init, totalpacket
    ser_bytes_init = ser.read_until(expected=b"\xff\xff\xff", size=244)
    totalpacket = totalpacket + 1
    id_number = ser_bytes[0:1].hex()
    pkt_cnt = ser_bytes[2]
    queue.put(ser_bytes)

    if id_number == "31":
        queueArraynode1.put(ser_bytes)
    if id_number == "32":
        queueArraynode2.put(ser_bytes)
    if id_number == "33":
        queueArraynode3.put(ser_bytes)
    if id_number == "34":
        queueArraynode4.put(ser_bytes)
    if id_number == "35":
        queueArraynode5.put(ser_bytes)
    if id_number == "36":
        queueArraynode6.put(ser_bytes)

if __name__ == "__main__":
    ## Set the portName to the appropriate serial port on macOS
    # portName = "/dev/tty.usbserial-XXXXXXXX"  # Replace with the actual device name
    # baudrate = 921600
    # ser = serial.Serial(portName, baudrate, timeout=None)
    # ser.flushInput()
    
    ## You can find the list of connected serial devices using the following command in the terminal:
    # ls /dev/tty.*
    
    ## Set the portName to the appropriate serial port on macOS
    portName = "COM6"
    baudrate = 921600
    ser = serial.Serial(portName, baudrate,timeout = None)
    ser.flushInput()

    start = time.time()
    queue = multiprocessing.Queue()
    queueArraynode1 = multiprocessing.Queue()
    queueArraynode2 = multiprocessing.Queue()
    queueArraynode3 = multiprocessing.Queue()
    queueArraynode4 = multiprocessing.Queue()
    queueArraynode5 = multiprocessing.Queue()
    queueArraynode6 = multiprocessing.Queue()
    queuenode1Bytes = multiprocessing.Queue()
    queuenode2Bytes = multiprocessing.Queue()
    queuenode3Bytes = multiprocessing.Queue()
    queuenode4Bytes = multiprocessing.Queue()
    queuenode5Bytes = multiprocessing.Queue()
    queuenode6Bytes = multiprocessing.Queue()
    stopped = threading.Event()


while True:
    try:
        QtCore.QCoreApplication.processEvents()
        p1 = threading.Thread(target=ReadFunction, args=(queue,))
        p3 = threading.Thread(target=ReadBytenode, args=(queueArraynode1,queuenode1Bytes,))
        p4 = threading.Thread(target=UpdateGraphnode, args=(queuenode1Bytes,Val1,curve1,ptr1,))
        p5 = threading.Thread(target=ReadBytenode, args=(queueArraynode2, queuenode2Bytes,))
        p6 = threading.Thread(target=UpdateGraphnode, args=(queuenode2Bytes,Val2,curve2,ptr2,))
        p7 = threading.Thread(target=ReadBytenode, args=(queueArraynode3, queuenode3Bytes,))
        p8 = threading.Thread(target=UpdateGraphnode, args=(queuenode3Bytes,Val3,curve3,ptr3,))
        p9 = threading.Thread(target=ReadBytenode, args=(queueArraynode4, queuenode4Bytes,))
        p10 = threading.Thread(target=UpdateGraphnode, args=(queuenode4Bytes,Val4,curve4,ptr4,))
        p11 = threading.Thread(target=ReadBytenode, args=(queueArraynode5, queuenode5Bytes,))
        p12 = threading.Thread(target=UpdateGraphnode, args=(queuenode5Bytes,Val5,curve5,ptr5,))
        p13 = threading.Thread(target=ReadBytenode, args=(queueArraynode6, queuenode6Bytes,))
        p14 = threading.Thread(target=UpdateGraphnode, args=(queuenode6Bytes,Val6,curve6,ptr6,))
        p1.start()
        p3.start()
        p4.start()
        p5.start()
        p6.start()
        p7.start()
        p8.start()
        p9.start()
        p10.start()
        p11.start()
        p12.start()
        p13.start()
        p14.start()
        p1.join()
    except:
        print("Keyboard Interrupt")
        stop = time.time()
        print("elapsed time:",stop-start)
        break
pg.QtGui.QApplication.exec_()

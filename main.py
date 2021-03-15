from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
import mido
import sys
from threading import Thread
import time
import zipfile
import math

# libjack-jackd2-dev
# libasound2-dev

'''
TODO
-> load program from file
-> load program sysex
'''


class MidiThread(Thread, QObject):
    sig_control_change = pyqtSignal(int, dict)
    sig_params = pyqtSignal(bytes)

    def __init__(self):
        QObject.__init__(self)
        Thread.__init__(self)
        self._need_run = True
        print("OUTPUT", mido.get_output_names())
        print("INPUT", mido.get_input_names())

        # mido.read_syx_file()
        self.params = {}
        self.controls = {}
        self.controls_ignore = [63]

        self.outport = mido.open_output('minilogue xd:minilogue xd MIDI 2 20:1')

    def stop(self):
        self._need_run = False

    def data_to_sysex(self, data):
        sysex = [0]
        idx = 0
        cnt7 = 0

        for x in data:
            c = x & 0x7F
            msb = x >> 7
            sysex[idx] |= msb << cnt7
            sysex += [c]

            if cnt7 == 6:
                idx += 8
                sysex += [0]
                cnt7 = 0
            else:
                cnt7 += 1

        if cnt7 == 0:
            sysex.pop()

        return sysex

    def load_program(self):
        # Test
        print("SEND sysex")
        self.outport.send(mido.Message('sysex', data=[0x7E, 0x00, 0x06, 0x01]))

        # # open and read the file
        # with zipfile.ZipFile("ReplicantXD.mnlgxdprog", mode='r') as file:
        #     try:
        #         fileContent = file.read('Prog_%03d.prog_bin' % (0,))
        #     except:
        #         print("Couldn't open file. Check program number and file name.")
        #         exit(-2)
        #
        # self.sig_params.emit(fileContent)
        # with mido.open_output('minilogue xd:minilogue xd MIDI 2 20:1') as outport:
        #     msg = mido.Message('sysex', data=[40])
        #     outport.send(msg)

    def run(self):
        with mido.open_input('minilogue xd:minilogue xd MIDI 2 20:1') as inport:
            while self._need_run:
                message = inport.receive()
                if message.type == 'control_change':
                    self.controls[message.control] = message.value
                    if not message.control in self.controls_ignore:
                        self.sig_control_change.emit(message.control, self.controls)
                if message.type != 'clock':
                    print(message)


    def send_cc(self, cc, value):
        print("SEND CC")
        msg = mido.Message('control_change')
        msg.control = cc
        msg.value = value

        self.outport.send(msg)


class MainWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.setWindowTitle("Monologue XD Editor Guigui")
        self.setLayout(QHBoxLayout())
        self.midi = MidiThread()
        self.midi.sig_control_change.connect(lambda c, d: self.slot_cc(c, d))
        self.midi.sig_params.connect(lambda d: self.slot_program_read(d))

        self.midi.start()
        self.synth = self.load_synth_panel()

        self.midi.load_program()

    def load_synth_panel(self):
        # GROUP, DESC, BUFFER START, BUFFER SIZE, CONTROL CHANGE, DATATYPE, WIDGETTYPE, COMBO, DESC, INFO
        synth = {}
        grouplist = []
        with open("monologue.csv", 'r') as file:
            lines = file.readlines()
            i = 0
            for l in lines:
                if i:
                    l=l.split(',')
                    group = l[0]
                    if not group in grouplist:
                        grouplist.append(group)
                    name = l[1]
                    elmt = {"GROUP": l[0],
                            "START": int(l[2]),
                            "SIZE": int(l[3]),
                            "CC": l[4],
                            "DTYPE": l[5],
                            "WTYPE": l[6],
                            "COMBO": l[7].split(' '),
                            "WIDGET": None}
                    synth[name] = elmt
                i += 1

        print("Create grouplist:", grouplist)
        # populate
        groupboxes = []
        for gr in grouplist:
            gb = QGroupBox(gr)
            gb.setObjectName(gr)
            gb.setLayout(QGridLayout())
            groupboxes.append(gb)

            self.layout().addWidget(groupboxes[-1])

        # Populate object

        for elmt in synth:
            obj = synth[elmt]
            gbname = obj["GROUP"]
            groupbox = self.findChild(QGroupBox, gbname)
            if obj["WTYPE"] == "SLIDER":
                slider = QSlider()
                slider.setObjectName(elmt)
                slider.setOrientation(Qt.Horizontal)
                slider.setRange(0, 127 if obj["DTYPE"] == "INT" else 1023)
                groupbox.layout().addWidget(QLabel(elmt))
                groupbox.layout().addWidget(slider)
                obj["WIDGET"] = slider
                obj["WIDGET"].sliderMoved.connect(lambda : self.slot_change_params())
            elif obj["WTYPE"].startswith("COMBO"):
                combo = QComboBox()
                combo.setObjectName(elmt)
                combo.addItems(obj["COMBO"])
                groupbox.layout().addWidget(QLabel(elmt))
                groupbox.layout().addWidget(combo)
                obj["WIDGET"] = combo
                obj["WIDGET"].activated.connect(lambda: self.slot_change_params())
        return synth

    def slot_change_params(self):
        sender = self.sender()
        name = sender.objectName()
        if type(sender) == QSlider:
            value = self.sender().value()
        elif type(sender) == QComboBox:
            combo_4 = [0, 42, 84, 127]
            combo_3 = [0, 64, 127]
            combo_2 = [0, 127]
            if len(self.synth[name]["COMBO"]) == 2:
                value = combo_2[self.sender().currentIndex()]
            elif len(self.synth[name]["COMBO"]) == 3:
                value = combo_3[self.sender().currentIndex()]
            elif len(self.synth[name]["COMBO"]) == 4:
                value = combo_4[self.sender().currentIndex()]
        cc = int(self.synth[name]["CC"])
        print("User set {} to {}".format(name, value))
        if self.synth[name]["DTYPE"] == "INT10":
            self.midi.send_cc(63, value % 8)
            self.midi.send_cc(cc, math.floor(value/8))
        elif self.synth[name]["DTYPE"] == "INT":
            self.midi.send_cc(cc, value)

    def slot_cc(self, last, ccs):
        combo_4 = [0, 42, 84, 127]
        combo_3 = [0, 64, 127]
        combo_2 = [0, 127]
        print(last)
        name = "None"
        for key in self.synth:
            print(key, self.synth[key]["CC"])
            if self.synth[key]["CC"] != '':
                if int(self.synth[key]["CC"]) == last:
                    name = key
                    break

        print("Minilogue set {} at {}-@63={}".format(name, ccs[last], ccs[63] if 63 in ccs.keys() else 0))
        dtype = self.synth[name]["DTYPE"]
        widget = self.synth[name]["WIDGET"]

        if dtype == "INT":
            if type(widget) == QSlider:
                widget.setValue(ccs[last])
            elif type(widget) == QComboBox:
                if len(self.synth[key]["COMBO"]) == 2:
                    widget.setCurrentIndex(combo_2.index(ccs[last]))
                elif len(self.synth[key]["COMBO"]) == 3:
                    widget.setCurrentIndex(combo_3.index(ccs[last]))
                elif len(self.synth[key]["COMBO"]) == 4:
                    widget.setCurrentIndex(combo_4.index(ccs[last]))
        elif dtype == "INT10":
            widget.setValue(ccs[last] * 8 + ccs[63])

    def slot_program_read(self, params):
        print(params)
        max = len(self.synth)
        index = 0
        for key in self.synth:
            obj = self.synth[key]
            dtype = obj["DTYPE"]
            wtype = obj["WTYPE"]
            widget = obj['WIDGET']
            start = obj['START']
            size = obj['SIZE']

            if dtype.startswith("INT"):
                if wtype == "SLIDER":
                    widget.setValue(int.from_bytes(params[start:start+size], 'little'))
                elif wtype.startswith("COMBO"):
                    widget = self.findChild(QComboBox, key)
                    widget.setCurrentIndex(int.from_bytes(params[start:start + size], 'little'))

            index += 1

    def closeEvent(self, event):
        self.midi.stop()
        self.midi.join()
        QWidget.closeEvent(self, event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    widget = MainWidget()
    widget.show()
    app.exec()
    app.exit(0)
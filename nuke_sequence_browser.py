import os
import sys
import re
import datetime
import glob
from io import BytesIO

import numpy
import imageio
import pymongo
import base64
from bson.binary import Binary
from functools import partial
from PIL import Image
from pathlib import Path
from PySide2 import QtGui as gui
from PySide2 import QtCore as core
from PySide2 import QtWidgets as wdg
# import nuke


#
# def get_main_window():
#     q_app = wdg.QApplication.instance()
#     for widget in q_app.topLevelWidgets():
#         if widget.metaObject().className() == "Foundry::UI::DockMainWindow":
#             return widget

#todo implement my custom mousePressEvent
class MyQFrame(wdg.QLabel):
    clicked = core.Signal(str)
    def __init__(self):
        super(MyQFrame, self).__init__()

    def mousePressEvent(self, e):
        return self.text()

class TagBar(wdg.QWidget):
    def __init__(self):
        super(TagBar, self).__init__()
        self.setWindowTitle('Tag Bar')
        self.tags = []
        self.h_layout = wdg.QHBoxLayout()
        self.h_layout.setSpacing(4)
        self.setLayout(self.h_layout)
        self.line_edit = wdg.QLineEdit()
        self.line_edit.setSizePolicy(wdg.QSizePolicy.Minimum, wdg.QSizePolicy.Maximum)
        self.setSizePolicy(wdg.QSizePolicy.Minimum, wdg.QSizePolicy.Minimum)
        self.setContentsMargins(2,2,2,2)
        self.h_layout.setContentsMargins(2,2,2,2)
        self.refresh()
        self.setup_ui()
        self.show()

    def setup_ui(self):
        self.line_edit.returnPressed.connect(self.create_tags)

    def create_tags(self):
        new_tags = self.line_edit.text().split(', ')
        print( new_tags)
        self.line_edit.setText('')
        self.tags.extend(new_tags)
        self.tags = list(set(self.tags))
        self.tags.sort(key=lambda x: x.lower())
        self.refresh()

    def refresh(self):
        for i in reversed(range(self.h_layout.count())):
            self.h_layout.itemAt(i).widget().setParent(None)
        for tag in self.tags:
            self.add_tag_to_bar(tag)
        self.h_layout.addWidget(self.line_edit)
        self.line_edit.setFocus()

    def add_tag_to_bar(self, text):
        tag = wdg.QFrame()
        tag.setStyleSheet('border:1px solid rgb(192, 192, 192); border-radius: 4px;')
        tag.setContentsMargins(2, 2, 2, 2)
        tag.setFixedHeight(28)
        hbox = wdg.QHBoxLayout()
        hbox.setContentsMargins(4, 4, 4, 4)
        hbox.setSpacing(10)
        tag.setLayout(hbox)
        label = MyQFrame()
        label.setText(text)
        label.clicked.connect(self.test_label)
        # label = wdg.QLabel(text)
        label.setStyleSheet('border:0px')
        label.setFixedHeight(16)
        hbox.addWidget(label)
        x_button = wdg.QPushButton('x')
        x_button.setFixedSize(20, 20)
        x_button.setStyleSheet('border:0px; font-weight:bold')
        x_button.setSizePolicy(wdg.QSizePolicy.Maximum, wdg.QSizePolicy.Maximum)
        x_button.clicked.connect(partial(self.delete_tag, text))
        x_button.clicked.connect(text)
        hbox.addWidget(x_button)
        tag.setSizePolicy(wdg.QSizePolicy.Maximum,wdg.QSizePolicy.Preferred)
        self.h_layout.addWidget(tag)

    def test_label(self, text):
        print(text)

    def delete_tag(self, tag_name):
        self.tags.remove(tag_name)
        self.refresh()

    def test_print(self, text):
        print(text)


class Panel(wdg.QMainWindow):
    # def __init__(self, parent=get_main_window()):
    #     super(Panel, self).__init__(parent)

    def __init__(self):
        super(Panel, self).__init__()

        self.ATTR_ROLE = core.Qt.UserRole
        self.VALUE_ROLE = core.Qt.UserRole + 1

        self.init_sb()

        self.seg_data = {}
        self.all_data = []
        self.seq_format = 'exr'

        #all seq in db
        self.all_db_seq = [seq['name'] for seq in self.SEQ_COLLECTION.find({}, {"name": 1, "_id": 0})]


        self.test_in_progress = False

        self.setWindowTitle("Sequence Explorer")
        self.setMinimumWidth(800)
        self.setMinimumHeight(800)

        self.create_widgets()
        self.create_layout()
        self.create_connections()

    def create_widgets(self):
        self.tag_bar = TagBar()

        self.filepath_le = wdg.QLineEdit()
        self.select_file_path = wdg.QPushButton("Select Path")
        self.select_file_path.setToolTip("Select Sequence")
        self.select_file_path.setStyleSheet("background-color:#c47f00; color: black;")

        self.search_bar_lbl = wdg.QLabel("Filter Seq: ")
        self.search_bar_le = wdg.QLineEdit()

        #### Start Progressbar wdg ####

        self.progress_bar_label = wdg.QLabel("Generating Thumbnails")
        self.progress_bar = wdg.QProgressBar()

        self.update_visibility()

        self.save_to_db_btn = wdg.QPushButton("Save to DB")
        self.load_from_btn = wdg.QPushButton("Load from DB")

        #### End Progressbar wdg ####

        #table widget
        self.table_wdg = wdg.QTableWidget()
        self.table_wdg.setShowGrid(False)
        #hacemos la tabla de solo lectura
        self.table_wdg.setEditTriggers(wdg.QTableWidget.NoEditTriggers)
        #self.set_path_btn = wdg.QPushButton("Choose Dir")
        self.table_wdg.setColumnCount(6)
        self.table_wdg.setColumnWidth(0, 256)  #imagen
        self.table_wdg.setColumnWidth(1, 200) #seqname
        self.table_wdg.setColumnWidth(2, 80) #frames
        self.table_wdg.setColumnWidth(3, 80) #mixing frame
        self.table_wdg.setColumnWidth(4, 80) #load scene
        self.table_wdg.setColumnWidth(5, 150) #load scene
        self.table_wdg.setHorizontalHeaderLabels(["Thumbnail", "Sequence Name", "NFrames", "Mix Frame", "Load Scene", "last Mod"])
        header_view = self.table_wdg.horizontalHeader()
        header_view.setSectionResizeMode(1, wdg.QHeaderView.Stretch)

    def create_layout(self):
        buttons_lyt = wdg.QHBoxLayout()
        buttons_lyt.addWidget(self.search_bar_lbl)
        buttons_lyt.addWidget(self.search_bar_le)
        buttons_lyt.addWidget(self.filepath_le)
        buttons_lyt.addWidget(self.select_file_path)

        tag_lyt = wdg.QHBoxLayout()
        tag_lyt.addWidget(self.tag_bar)

        db_btn_lyt = wdg.QHBoxLayout()
        db_btn_lyt.addWidget(self.save_to_db_btn)
        db_btn_lyt.addWidget(self.load_from_btn)

        #### Start Progressbar wdg ####
        progress_bar_lyt = wdg.QHBoxLayout()
        progress_bar_lyt.addWidget(self.progress_bar_label)
        progress_bar_lyt.addWidget(self.progress_bar)
        #### end Progressbar wdg ####

        main_lyt = wdg.QVBoxLayout()
        main_lyt.setContentsMargins(3, 3, 3, 3)
        main_lyt.setSpacing(3)
        main_lyt.addLayout(buttons_lyt)
        main_lyt.addLayout(tag_lyt)
        main_lyt.addWidget(self.table_wdg)
        main_lyt.addLayout(progress_bar_lyt)
        main_lyt.addLayout(db_btn_lyt)

        widget = wdg.QWidget()
        widget.setLayout(main_lyt)

        self.setCentralWidget(widget)

    def create_connections(self):
        self.select_file_path.clicked.connect(self.show_selected_file)
        self.search_bar_le.textChanged.connect(self.update_display)
        self.save_to_db_btn.clicked.connect(self.seq_to_db)
        self.load_from_btn.clicked.connect(self.load_from_db)

    ### progressbar visibility ###
    def update_visibility(self):
        self.progress_bar_label.setVisible(self.test_in_progress)
        self.progress_bar.setVisible(self.test_in_progress)

    def update_display(self, text):
        column = 1
        for row in range(self.table_wdg.rowCount()):
            item = self.table_wdg.item(row, column)
            if item:
                # if not text.lower() in item.text():
                #     self.table_wdg.setRowHidden(row,True)
                # else:
                #     self.table_wdg.setRowHidden(row, False)
                if item.text().lower().startswith(text.lower()):
                    self.table_wdg.setRowHidden(row, False)
                else:
                    self.table_wdg.setRowHidden(row, True)


    def show_selected_file(self):
        file_path = wdg.QFileDialog.getExistingDirectory(self, "Select Dir", "")
        if file_path:
            self.filepath_le.setText(file_path)
            self.seg_data = self.get_uniq_seq(self.get_files_of_type( file_path, self.seq_format))
            self.all_data = [v for k, v in self.seg_data.items()]
            self.update_table(self.all_data)
            self.seg_data = {}


    def update_table(self, all_data):
        self.table_wdg.clear()
        self.table_wdg.setRowCount(0)
        #all_data is a list of dict, each dict with name, etc..

        if self.test_in_progress:
            return

        self.progress_bar.setRange(0, len(all_data))
        self.progress_bar.setValue(0)
        self.progress_bar_label.setText("Operation in Progress")

        self.test_in_progress = True
        self.update_visibility()

        for i, seq in enumerate(all_data):
            #seq es un diccionario con el nombre de la secuencia, frames ,y resto de campos
            #todo si el seq['name'] esta en la db entonces seq es igual al seq de la db

            if seq['name'] in self.all_db_seq:
                seq = self.SEQ_COLLECTION.find_one({"name": seq['name']})
                img = seq["thumbnail"].rpartition(".")[0] + ".png"
                thumbnail_img = self.bin_to_img(img, seq['img_bin'])
                seq["thumbnail"] = thumbnail_img


            #todo decodificar la imagen y poner la como thumbnail


            if not self.test_in_progress:
                break
            self.progress_bar_label.setText("Genering Thumbnails: {0} (of {1})".format(i, len(all_data)))
            self.progress_bar.setValue(i)
            core.QCoreApplication.processEvents()


            self.table_wdg.insertRow(i)
            self.insert_item(i, 1, seq['name'], "", "")
            self.insert_item(i, 2, str(seq["num_frames"]), "", "")
            self.insert_item(i, 3, seq["mixing_frames"], "", "")
            self.insert_item(i, 5, seq["mod_time"], "", "")
            load_button = wdg.QPushButton("LOAD SCENE"), seq['name']
            load_button[0].setStyleSheet("background-color:#c47f00; color: black;")
            self.set_load_buttons(i, load_button)

            self.table_wdg.setRowHeight(i, 128)
            if seq["thumbnail"].endswith('.exr'):
                self.set_thumbnail_image(i, seq["thumbnail"])
            else:
                self.create_thumbnail_widget(i, seq["thumbnail"])

        self.test_in_progress = False
        self.update_visibility()

    def insert_item(self, row, column, text, attr, value):
        item = wdg.QTableWidgetItem(text)
        item.setTextAlignment( core.Qt.AlignHCenter | core.Qt.AlignVCenter)
        self.set_item_attr(item, attr)
        self.set_item_value(item, value)
        self.table_wdg.setItem(row, column, item)


    def set_thumbnail_image(self, i, image_path):

        source_image = image_path
        destiny = source_image.rpartition(".")[0] + ".png"
        if not os.path.exists(destiny):
            self.exr_to_jpg(source_image, destiny)
        self.create_thumbnail_widget(i, destiny)

    def create_thumbnail_widget(self, i, thumb_image):

        pic = gui.QPixmap(thumb_image)
        self.thumbnail_label = wdg.QLabel("")
        self.thumbnail_label.setScaledContents(True)
        self.thumbnail_label.setPixmap(pic)
        self.table_wdg.setCellWidget(i, 0, self.thumbnail_label)

    def set_load_buttons(self, i, btn):
        self.table_wdg.setCellWidget(i, 4, btn[0])
        btn[0].clicked.connect(partial(self.load_scene, btn[1]))

    def load_scene(self, seq_name):
        # C:/Users/Miguel/Desktop/shows\showA\seq1\shot1\yate_all_elements.0030.png
        seq_thubnail = self.seg_data[seq_name]["thumbnail"]
        start_frame = str(self.seg_data[seq_name]["start_frame"]).lstrip("0")
        end_frame = str(self.seg_data[seq_name]["end_frame"]).lstrip("0")
        seq_path = os.path.splitext(seq_thubnail)[0].rpartition(".")[0] + '.####.exr'
        seq_path_fix_slash = Path(seq_path).as_posix()
        nuke.createNode("Read", "file {} first {} last {} origfirst {} origlast {}".format(seq_path_fix_slash,
                                                                              int(start_frame),
                                                                              int(end_frame),
                                                                            int(start_frame),
                                                                            int(end_frame)))

    #Start Helper Functions#

    def set_item_attr(self, item, attr):
        item.setData(self.ATTR_ROLE, attr)

    def set_item_value(self, item, value):
        item.setData(self.VALUE_ROLE, value)

    def get_item_value(self, item):
        return item.data(self.VALUE_ROLE)


    def get_files_of_type(self, destinationDir, fileType):
        for x in os.walk(destinationDir):
            for y in glob.glob(os.path.join(x[0], '*.{0}'.format(fileType))):
                yield y

    def get_frames(self, file):
        pattern = re.compile(r'(\d){4}')
        if pattern.findall(file):
            mo = pattern.search(file)
            frame = mo.group()
            return frame

    def get_last_modified(self, file):
        mod_datetime = os.path.getmtime(file)
        mod_time = datetime.datetime.utcfromtimestamp(mod_datetime).strftime('%d-%m-%y %H:%M:%S')
        return mod_time

    def fix_backslash(self, file_path):
        object_path = Path(file_path)
        return object_path.as_posix()

    def get_uniq_seq(self, file_list):
        for file in file_list:
            full_file_path = Path(file)
            seq_name = full_file_path.stem.rpartition(".")[0]
            if seq_name != "":
                self.seg_data[seq_name] = self.seg_data.get(seq_name, {})
                self.seg_data[seq_name]['name'] = seq_name
                self.seg_data[seq_name]['dir'] = str(self.fix_backslash(full_file_path.parent))
                self.seg_data[seq_name]['frames'] = self.seg_data[seq_name].get('frames', [])
                self.seg_data[seq_name]['frames'].append(self.get_frames(file))
                self.seg_data[seq_name]['start_frame'] = self.seg_data[seq_name]['frames'][0]
                self.seg_data[seq_name]['end_frame'] = self.seg_data[seq_name]['frames'][-1]
                self.seg_data[seq_name]['num_frames'] = len(self.seg_data[seq_name]['frames'])
                self.seg_data[seq_name]['mod_time'] = self.get_last_modified(file)
                self.seg_data[seq_name]['thumbnail'] = self.fix_backslash("{0}/{1}.{2}.exr".format(self.seg_data[seq_name]['dir'],
                                                                                         seq_name,
                                                                                         self.seg_data[seq_name][
                                                                                             'start_frame']))
                frame_range = (int(self.seg_data[seq_name]['end_frame']) - int(self.seg_data[seq_name]['start_frame'])) + 1
                self.seg_data[seq_name]['mixing_frames'] = "Yes" if self.seg_data[seq_name]['num_frames'] != frame_range else "Not"

        return self.seg_data

    def exr_to_jpg(self, exr_file, jpg_file):
        if not os.path.isfile(exr_file):
            return False

        filename, extension = os.path.splitext(exr_file)
        if not extension.lower().endswith('.exr'):
            return False

        # imageio.plugins.freeimage.download() #DOWNLOAD IT
        image = imageio.imread(exr_file)
        im_gamma_correct = numpy.clip(numpy.power(image, 0.45), 0, 1)
        # pil image
        im_fixed = Image.fromarray(numpy.uint8(im_gamma_correct * 255))
        im_fixed.thumbnail((256, 256))
        im_fixed.save(jpg_file, "png")

    ### Save and Load to DB ###

    def init_sb(self):
        # DB conexion data
        SERVER = pymongo.MongoClient('mongodb://127.0.0.1:27017/')
        DB = SERVER["SEQ_DB"]
        # creamos dos collections en la base de datos clipboard userCollections y clipboardCollections
        self.SEQ_COLLECTION = DB['sequences']

    # def convert_img_to_bin(self, img):
    #
    #     im = Image.open(img)
    #     imgByteArr = io.BytesIO()
    #     im.save(imgByteArr, format='PNG')
    #     image = {"img_bin": imgByteArr.getvalue()}
    #     return image

    def convert_img_to_bin(self, img):

        with open(img, "rb") as imageFile:
            img_bin = base64.b64encode(imageFile.read())
        return img_bin

    def bin_to_img(self, img, bin_image):
        # with open(img, "wb") as fimage:
        #     fimage.write(bin_image.decode('utf-8'))
        im = Image.open(BytesIO(base64.b64decode(bin_image)))
        im.save(img, 'PNG')
        return img

    # from PIL import Image
    # from bson import Binary
    #
    # img = Image.open('test.jpg')
    #
    # imgByteArr = io.BytesIO()
    # img.save(imgByteArr, format='PNG')
    # imgByteArr = imgByteArr.getvalue()
    def seq_to_db(self):
        for seq in self.all_data:
            if not self.SEQ_COLLECTION.find_one({"name": seq['name']}):
                # self.save_to_db(seq)
                self.SEQ_COLLECTION.insert_one(seq)
        self.update_seq_with_thumb()

    def update_seq_with_thumb(self):
        for seq in self.all_data:
            thumb_png = seq["thumbnail"].rpartition(".")[0] + ".png"
            image_data = self.convert_img_to_bin(thumb_png)
            # print(self.SEQ_COLLECTION.find())
            self.SEQ_COLLECTION.find_one_and_update({"name": seq['name']}, {"$set": {"img_bin": image_data}}, upsert=True)

    def load_from_db(self):

        all_db_seq = [seq for seq in self.SEQ_COLLECTION.find({}, {"_id": 0})]
        self.update_table(all_db_seq) #list of dict with sequence data



app = wdg.QApplication(sys.argv)
seq_explorer = Panel()
app.setStyle(wdg.QStyleFactory.create("fusion"))

dark_palette = gui.QPalette()
dark_palette.setColor(gui.QPalette.Window, gui.QColor(45, 45, 45))
dark_palette.setColor(gui.QPalette.WindowText, gui.QColor(208, 208, 208))
dark_palette.setColor(gui.QPalette.Base, gui.QColor(25, 25, 25))
dark_palette.setColor(gui.QPalette.AlternateBase, gui.QColor(208, 208, 208))
dark_palette.setColor(gui.QPalette.ToolTipBase, gui.QColor(208, 208, 208))
dark_palette.setColor(gui.QPalette.ToolTipBase, gui.QColor(208, 208, 208))
dark_palette.setColor(gui.QPalette.Text, gui.QColor(208, 208, 208))
dark_palette.setColor(gui.QPalette.Button, gui.QColor(45, 45, 48))
dark_palette.setColor(gui.QPalette.ButtonText, gui.QColor(208, 208, 208))
dark_palette.setColor(gui.QPalette.BrightText, core.Qt.red)
dark_palette.setColor(gui.QPalette.Link, gui.QColor(42, 130, 218))
dark_palette.setColor(gui.QPalette.Highlight, gui. QColor(42, 130, 218))
dark_palette.setColor(gui.QPalette.Highlight, core.Qt.black)
app.setPalette(dark_palette)
seq_explorer.show()
app.exec_()
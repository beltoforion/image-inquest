from __future__ import annotations

import cv2

from enum import Enum
from core.io_data import IoDataType
from core.node_base import SinkNodeBase, InputPort

import os


class OutputFormat(Enum):
    SAME_AS_INPUT = 0
    GIF = 1
    PNG = 2


class FileSink(SinkNodeBase):
    def __init__(self):
        super().__init__("File Sinke")
        
        self.__output_path = "out.png"
        self.__output_format = OutputFormat.SAME_AS_INPUT

        self._add_input(InputPort("image", {IoDataType.IMAGE}))


    @property
    def output_format(self):
        return self.__output_format


    @output_format.setter
    def output_format(self, output_format):
        self.__output_format = output_format


    @property
    def output_path(self):
        return self.__output_path


    @output_path.setter
    def output_path(self, output_path):
        self.__output_path = output_path


    def process(self):
        file_name, file_ext = os.path.splitext(self.output_path)
        
        if self.__output_format==OutputFormat.SAME_AS_INPUT:
            output = file_name + file_ext
        elif self.__output_format==OutputFormat.PNG:
            output = file_name + ".png"
        else:
            raise(Exception("Invalid output format"))
        
        cv2.imwrite(output, self.inputs[0].data.image)
        cv2.imshow(output, self.inputs[0].data.image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


    def end_of_series(self):
        pass


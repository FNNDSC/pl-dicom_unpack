#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter

from chris_plugin import chris_plugin, PathMapper
import pydicom as dicom
import matplotlib.pyplot as plt
import os
import cv2
import PIL  # optional
import pandas as pd
import csv

__version__ = '1.0.0'

DISPLAY_TITLE = r"""
ChRIS Plugin Template Title
"""

parser = ArgumentParser(description='!!!CHANGE ME!!! An example ChRIS plugin which '
                                    'counts the number of occurrences of a given '
                                    'word in text files.',
                        formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument('-f', '--fileFilter', default='dcm', type=str,
                    help='input file filter glob')
parser.add_argument('-t', '--outputType', default='dcm', type=str,
                    help='input file filter glob')
parser.add_argument('-V', '--version', action='version',
                    version=f'%(prog)s {__version__}')


# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin
@chris_plugin(
    parser=parser,
    title='My ChRIS plugin',
    category='',  # ref. https://chrisstore.co/plugins
    min_memory_limit='100Mi',  # supported units: Mi, Gi
    min_cpu_limit='1000m',  # millicores, e.g. "1000m" = 1 CPU core
    min_gpu_limit=0  # set min_gpu_limit=1 to enable GPU
)
def main(options: Namespace, inputdir: Path, outputdir: Path):
    """
    *ChRIS* plugins usually have two positional arguments: an **input directory** containing
    input files and an **output directory** where to write output files. Command-line arguments
    are passed to this main method implicitly when ``main()`` is called below without parameters.

    :param options: non-positional arguments parsed by the parser given to @chris_plugin
    :param inputdir: directory containing (read-only) input files
    :param outputdir: directory where to write output files
    """

    print(DISPLAY_TITLE)

    # Typically it's easier to think of programs as operating on individual files
    # rather than directories. The helper functions provided by a ``PathMapper``
    # object make it easy to discover input files and write to output files inside
    # the given paths.
    #
    # Refer to the documentation for more options, examples, and advanced uses e.g.
    # adding a progress bar and parallelism.
    mapper = PathMapper.file_mapper(inputdir, outputdir, glob=f"**/*.{options.fileFilter}")
    for input_file, output_file in mapper:
        dicom_file = read_dicom(str(input_file))
        if dicom_file is None:
            continue
        split_dicom_multiframe(dicom_file, input_file.name,output_file)



if __name__ == '__main__':
    main()

def split_dicom_multiframe(dicom_data_set, image, output_file):
    image = image.replace('.dcm', '')
    dir_path = os.path.join(str(output_file))
    os.makedirs(dir_path, exist_ok=True)

    for i, slice in enumerate(dicom_data_set.pixel_array):
        dicom_data_set.PixelData = slice
        op_dcm_path = os.path.join(dir_path, f'slice_{i:03n}.dcm')
        dicom_data_set.save_as(op_dcm_path)


def read_dicom(dicom_path):
    dataset = None
    try:
        dataset = dicom.dcmread(dicom_path)
    except Exception as ex:
        print(dicom_path, ex)
    return dataset

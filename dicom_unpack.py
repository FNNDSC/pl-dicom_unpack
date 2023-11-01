#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter
import numpy as np
from chris_plugin import chris_plugin, PathMapper
import pydicom as dicom
import os
import csv
from pflog import pflog
from pftag import pftag
__version__ = '1.1.2'

DISPLAY_TITLE = r"""
       _           _ _                                                   _    
      | |         | (_)                                                 | |   
 _ __ | |______ __| |_  ___ ___  _ __ ___   _   _ _ __  _ __   __ _  ___| | __
| '_ \| |______/ _` | |/ __/ _ \| '_ ` _ \ | | | | '_ \| '_ \ / _` |/ __| |/ /
| |_) | |     | (_| | | (_| (_) | | | | | || |_| | | | | |_) | (_| | (__|   < 
| .__/|_|      \__,_|_|\___\___/|_| |_| |_| \__,_|_| |_| .__/ \__,_|\___|_|\_\
| |                                     ______         | |                    
|_|                                    |______|        |_|                    
""" + "\t\t -- version " + __version__ + " --\n\n"

parser = ArgumentParser(description='A ChRIS plugin to unpack individual dicom slices from a volume dicom file',
                        formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument('-f', '--fileFilter', default='dcm', type=str,
                    help='input file filter glob')
parser.add_argument('-t', '--outputType', default='dcm', type=str,
                    help='output file type')
parser.add_argument('-V', '--version', action='version',
                    version=f'%(prog)s {__version__}')
parser.add_argument(  '--pftelDB',
                    dest        = 'pftelDB',
                    default     = '',
                    type        = str,
                    help        = 'optional pftel server DB path')


# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin
@chris_plugin(
    parser=parser,
    title='A ChRIS plugin to unpack multi-frame dicom file to individual slices',
    category='',  # ref. https://chrisstore.co/plugins
    min_memory_limit='2Gi',  # supported units: Mi, Gi
    min_cpu_limit='2000m',  # millicores, e.g. "1000m" = 1 CPU core
    min_gpu_limit=0  # set min_gpu_limit=1 to enable GPU
)
@pflog.tel_logTime(
            event       = 'dicom_unpack',
            log         = 'Unpack dicom slices from a single multiframe dicom'
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
        split_dicom_multiframe(dicom_file, output_file)


if __name__ == '__main__':
    main()

def split_dicom_multiframe(dicom_data_set, output_file):
    """
    A method to split a 3D dicom file to individual 2D dicom
    slices
    """
    dir_path = str(output_file).replace('.dcm', '')
    print(f"Creating o/p directory: {dir_path}")
    os.makedirs(dir_path, exist_ok=True)

    for i, slice in enumerate(dicom_data_set.pixel_array):
        dicom_data_set.PixelData = slice.tobytes()
        dicom_data_set.NumberOfFrames = 1
        op_dcm_path = os.path.join(dir_path, f'slice_{i:03n}.dcm')
        print(f"Saving file : -->slice_{i:03n}.dcm<--")
        dicom_data_set.save_as(op_dcm_path)


def read_dicom(dicom_path:str):
    """
    A method to read a dicom file and return the dicom dataset
    """
    print(f"Reading dicom file : -->{dicom_path}<--")
    dataset = None
    try:
        dataset = dicom.dcmread(dicom_path)
    except Exception as ex:
        print(dicom_path, ex)
    return dataset

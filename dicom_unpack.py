#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter
import numpy as np
from chris_plugin import chris_plugin, PathMapper
import pydicom as dicom
import os
import tempfile
from    jobController       import jobber

__version__ = '1.3.4'

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


# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin
@chris_plugin(
    parser=parser,
    title='A ChRIS plugin to unpack multi-frame dicom file to individual slices',
    category='',  # ref. https://chrisstore.co/plugins
    min_memory_limit='8Gi',  # supported units: Mi, Gi
    min_cpu_limit='2000m',  # millicores, e.g. "1000m" = 1 CPU core
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

    mapper = PathMapper.file_mapper(inputdir, outputdir, glob=f"**/*.{options.fileFilter}",fail_if_empty=False)
    for input_file, output_file in mapper:
        dicom_file = read_dicom(str(input_file))
        if dicom_file is None:
            continue
        split_dicom_multiframe(dicom_file, output_file)
        del dicom_file  # release the pydicom Dataset (and its PixelData buffer)

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

    rows = dicom_data_set.Rows
    cols = dicom_data_set.Columns
    bits_allocated = dicom_data_set.BitsAllocated
    samples_per_pixel = getattr(dicom_data_set, 'SamplesPerPixel', 1)
    bytes_per_pixel = bits_allocated // 8
    frame_size = rows * cols * bytes_per_pixel * samples_per_pixel

    num_frames = int(getattr(dicom_data_set, 'NumberOfFrames', 1))
    raw = dicom_data_set.PixelData  # single buffer, no per-frame copy yet

    if "YBR_FULL_422" in dicom_data_set.PhotometricInterpretation:
        dicom_data_set.PhotometricInterpretation = "YBR_FULL"
    dicom_data_set.NumberOfFrames = 1

    for i in range(num_frames):
        start = i * frame_size
        end = start + frame_size
        dicom_data_set.PixelData = raw[start:end]  # slice, not a decode
        op_dcm_path = os.path.join(dir_path, f'slice_{i:03n}.dcm')
        print(f"Saving file : -->slice_{i:03n}.dcm<--")
        dicom_data_set.save_as(op_dcm_path)

    del raw

def read_dicom(dicom_path:str):
    """
    A method to read a dicom file and return the dicom dataset
    """
    print(f"Reading dicom file : -->{dicom_path}<--")
    dataset = None
    tmp_decompressed_path = decompress_dicom(dicom_path)
    try:
        dataset = dicom.dcmread(tmp_decompressed_path)
    except Exception as ex:
        print(tmp_decompressed_path, ex)
    finally:
        if os.path.exists(tmp_decompressed_path):
            os.remove(tmp_decompressed_path)
    return dataset

def decompress_dicom(dicom_path: str):
    """
    Decompress a DICOM file using `dcmdjpeg` command found in `dcmtk` library
    """
    fd, tmp_path = tempfile.mkstemp(suffix='.dcm')
    os.close(fd)
    try:
        shell = jobber({'verbosity': 1, 'noJobLogging': True})
        str_cmd = f"dcmdjpeg {dicom_path} {tmp_path}"
        d_response = shell.job_run(str_cmd)
        print(f"Command: {d_response['cmd']}")
        if d_response['returncode']:
            print(f"Error: {d_response['stderr']}")
            raise Exception(d_response["stderr"])
        print("Response: File decompressed successfully.")
        return tmp_path
    except Exception:
        os.remove(tmp_path)
        raise

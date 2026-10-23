"""
Tests that malformed / unreadable DICOM inputs are skipped instead of
aborting the whole run.

DCMTK's ``dcmdjpeg`` is stubbed out so these tests run without DCMTK installed.
"""
import shutil
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

import dicom_unpack
from dicom_unpack import parser, main

DCMTK_ERROR = "F: Too many bytes requested: decompressing file: "


def make_multiframe(path: Path, frames: int = 3, rows: int = 4, cols: int = 4):
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.7"
    meta.MediaStorageSOPInstanceUID = generate_uid()

    ds = Dataset()
    ds.file_meta = meta
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.SamplesPerPixel = 1
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.NumberOfFrames = frames
    ds.PixelData = np.arange(rows * cols * frames, dtype=np.uint16).tobytes()
    ds.save_as(str(path), write_like_original=False)
    return ds


@pytest.fixture
def fake_dcmdjpeg(monkeypatch, tmp_path):
    """
    Replace ``decompress_dicom`` with a stand-in that copies the file to a
    temp path, or fails the way DCMTK does for any file with 'bad' in its name.
    """
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    def fake(dicom_path: str) -> str:
        if "bad" in Path(dicom_path).name:
            raise Exception(DCMTK_ERROR + dicom_path)
        out = scratch / (Path(dicom_path).stem + "_decompressed.dcm")
        shutil.copy(dicom_path, out)
        return str(out)

    monkeypatch.setattr(dicom_unpack, "decompress_dicom", fake)
    return scratch


def run(inputdir: Path, outputdir: Path, *extra):
    options = parser.parse_args(list(extra))
    main(options, inputdir, outputdir)


def slices(outputdir: Path, name: str):
    return sorted(p.name for p in (outputdir / name).glob("*.dcm"))


def test_good_file_is_unpacked(fake_dcmdjpeg, tmp_path):
    inputdir, outputdir = tmp_path / "in", tmp_path / "out"
    inputdir.mkdir()
    make_multiframe(inputdir / "good.dcm", frames=3)

    run(inputdir, outputdir)

    assert slices(outputdir, "good") == ["slice_000.dcm", "slice_001.dcm", "slice_002.dcm"]
    first = pydicom.dcmread(str(outputdir / "good" / "slice_000.dcm"))
    assert first.NumberOfFrames == 1
    assert len(first.PixelData) == 4 * 4 * 2


def test_decompression_failure_is_skipped(fake_dcmdjpeg, tmp_path, capsys):
    inputdir, outputdir = tmp_path / "in", tmp_path / "out"
    inputdir.mkdir()
    make_multiframe(inputdir / "good.dcm", frames=2)
    make_multiframe(inputdir / "bad_truncated.dcm", frames=2)

    run(inputdir, outputdir)  # must not raise

    assert slices(outputdir, "good") == ["slice_000.dcm", "slice_001.dcm"]
    assert not (outputdir / "bad_truncated").exists()
    out = capsys.readouterr().out
    assert "Skipping" in out and "bad_truncated.dcm" in out
    assert "Too many bytes requested" in out
    assert "Skipped 1 malformed/unreadable file(s)" in out


def test_non_dicom_file_is_skipped(fake_dcmdjpeg, tmp_path, capsys):
    inputdir, outputdir = tmp_path / "in", tmp_path / "out"
    inputdir.mkdir()
    make_multiframe(inputdir / "good.dcm", frames=2)
    (inputdir / "notdicom.dcm").write_text("this is not a DICOM file")

    run(inputdir, outputdir)

    assert slices(outputdir, "good") == ["slice_000.dcm", "slice_001.dcm"]
    assert not (outputdir / "notdicom").exists()
    out = capsys.readouterr().out
    assert "could not read DICOM" in out
    assert "Skipped 1 malformed/unreadable file(s)" in out


def test_unpack_failure_is_skipped(fake_dcmdjpeg, tmp_path, capsys):
    """A file that reads fine but lacks required attributes (e.g. Rows)."""
    inputdir, outputdir = tmp_path / "in", tmp_path / "out"
    inputdir.mkdir()
    make_multiframe(inputdir / "good.dcm", frames=2)
    ds = make_multiframe(inputdir / "norows.dcm", frames=2)
    del ds.Rows
    ds.save_as(str(inputdir / "norows.dcm"), write_like_original=False)

    run(inputdir, outputdir)

    assert slices(outputdir, "good") == ["slice_000.dcm", "slice_001.dcm"]
    out = capsys.readouterr().out
    assert "could not unpack" in out and "norows.dcm" in out
    assert "Skipped 1 malformed/unreadable file(s)" in out


def test_read_dicom_returns_none_on_decompress_error(fake_dcmdjpeg, tmp_path):
    bad = tmp_path / "bad.dcm"
    make_multiframe(bad)
    assert dicom_unpack.read_dicom(str(bad)) is None


def test_decompress_dicom_raises_and_cleans_up(monkeypatch):
    """The real decompress_dicom still raises on a dcmdjpeg error and removes its temp file."""
    created = {}

    class FakeJobber:
        def __init__(self, *_args, **_kwargs):
            pass

        def job_run(self, cmd):
            created["tmp"] = cmd.split()[-1].strip("'")
            return {"cmd": cmd, "returncode": 1, "stderr": DCMTK_ERROR}

    monkeypatch.setattr(dicom_unpack, "jobber", FakeJobber)

    with pytest.raises(Exception, match="Too many bytes requested"):
        dicom_unpack.decompress_dicom("/some/input file (1).dcm")
    assert not Path(created["tmp"]).exists()


def test_paths_with_spaces_are_quoted(monkeypatch):
    seen = {}

    class FakeJobber:
        def __init__(self, *_args, **_kwargs):
            pass

        def job_run(self, cmd):
            seen["cmd"] = cmd
            return {"cmd": cmd, "returncode": 0, "stderr": ""}

    monkeypatch.setattr(dicom_unpack, "jobber", FakeJobber)
    tmp = dicom_unpack.decompress_dicom("/data/my scan (1).dcm")
    try:
        assert "'/data/my scan (1).dcm'" in seen["cmd"]
    finally:
        Path(tmp).unlink(missing_ok=True)

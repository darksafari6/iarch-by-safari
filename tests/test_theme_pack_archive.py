# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Archive round trips and untrusted-member rejection."""
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from iarch.cli import theme_pack_archive as archive
from iarch.cli.theme_pack_validate import PackError

ROOT = Path(__file__).resolve().parents[1]


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_round_trip_and_force(self):
        file = self.path / 'pack.tar.gz'
        archive.export_pack(ROOT / 'data/themes/dynamic-reference', file)
        dest = self.path / 'packs'
        self.assertEqual(archive.import_pack(file, dest).name, 'dynamic-reference')
        with self.assertRaises(PackError):
            archive.import_pack(file, dest)
        self.assertTrue(archive.import_pack(file, dest, force=True).is_dir())

    def test_hostile_members(self):
        for name, kind in [('../escape', 'file'), ('/absolute', 'file'),
                           ('foo/link', 'symlink'), ('foo/run', 'executable')]:
            with self.subTest(name=name):
                file = self.path / 'hostile.tar.gz'
                with tarfile.open(file, 'w:gz') as tar:
                    info = tarfile.TarInfo(name)
                    if kind == 'symlink':
                        info.type = tarfile.SYMTYPE
                        info.linkname = '/etc/passwd'
                        tar.addfile(info)
                    else:
                        info.size = 1
                        info.mode = 0o755 if kind == 'executable' else 0o644
                        tar.addfile(info, io.BytesIO(b'x'))
                with self.assertRaises(PackError):
                    archive.import_pack(file, self.path / 'dest')

    def test_oversize(self):
        file = self.path / 'big.tar.gz'
        with file.open('wb') as f:
            f.truncate(archive.MAX_ARCHIVE + 1)
        with self.assertRaises(PackError):
            archive.import_pack(file, self.path / 'dest')


if __name__ == '__main__':
    unittest.main()

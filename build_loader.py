import os
import re
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
from subprocess import DEVNULL, PIPE, STDOUT
from urllib.request import urlopen

from PyQt5.QtCore import QThread, pyqtSignal

from _platform import get_platform

if get_platform() == 'Windows':
    from subprocess import CREATE_NO_WINDOW


class BuildLoader(QThread):
    finished = pyqtSignal('PyQt_PyObject')
    block_abortion = pyqtSignal()
    progress_changed = pyqtSignal(
        'PyQt_PyObject', 'PyQt_PyObject', 'PyQt_PyObject')

    def __init__(self, parent, url, strptime):
        QThread.__init__(self)
        self.parent = parent
        self.url = url
        self.strptime = strptime
        self.root_folder = self.parent.settings.value('root_folder')
        self.is_running = False
        self.platform = get_platform()

    def run(self):
        self.is_running = True
        blender_zip = urlopen(self.url)
        size = blender_zip.info()['Content-Length']
        temp_path = os.path.join(self.root_folder, "temp")
        path = os.path.join(temp_path, self.url.split('/', -1)[-1])

        # Create temp directory
        if not os.path.isdir(temp_path):
            os.makedirs(temp_path)

        # Download
        with open(path, 'wb') as file:
            while True:
                chunk = blender_zip.read(16 * 1024)

                if not chunk:
                    break

                file.write(chunk)
                progress = os.stat(path).st_size / int(size)
                self.progress_changed.emit(
                    progress, progress * 0.5, "Downloading: %p%")

                if not self.is_running:
                    file.close()
                    if os.path.isdir(temp_path):
                        shutil.rmtree(temp_path)
                    self.finished.emit(None)
                    return

        # Show extraction progress at 0
        self.progress_changed.emit(0, 0, "Extracting: %p%")

        # Extract
        if self.platform == 'Windows':
            zf = zipfile.ZipFile(path)
            version = zf.infolist()[0].filename.split('/')[0]
            uncompress_size = sum((file.file_size for file in zf.infolist()))
            extracted_size = 0

            for file in zf.infolist():
                zf.extract(file, self.root_folder)
                extracted_size += file.file_size
                progress = extracted_size / uncompress_size
                self.progress_changed.emit(
                    progress, progress * 0.5 + 0.5, "Extracting: %p%")

                if not self.is_running:
                    zf.close()
                    shutil.rmtree(os.path.join(self.root_folder, version))
                    if os.path.isdir(temp_path):
                        shutil.rmtree(temp_path)
                    self.finished.emit(None)
                    return

            zf.close()
        elif self.platform == 'Linux':
            tar = tarfile.open(path)
            version = tar.getnames()[0].split('/')[0]
            uncompress_size = sum((member.size for member in tar.getmembers()))
            extracted_size = 0

            for member in tar.getmembers():
                tar.extract(member, path=self.root_folder)
                extracted_size += member.size
                progress = extracted_size / uncompress_size
                self.progress_changed.emit(
                    progress, progress * 0.5 + 0.5, "Extracting: %p%")

                if not self.is_running:
                    tar.close()
                    shutil.rmtree(os.path.join(self.root_folder, version))
                    if os.path.isdir(temp_path):
                        shutil.rmtree(temp_path)
                    self.finished.emit(None)
                    return

            tar.close()

        self.block_abortion.emit()
        self.progress_changed.emit(0, 0, "Finishing...")

        # Delete temp folder
        if os.path.isdir(temp_path):
            shutil.rmtree(temp_path)

        # Make nice name for dir
        git = self.url.split('-',)[-2]
        nice_name = "Git-%s-%s" % \
            (git, time.strftime("%d-%b-%H-%M", self.strptime))

        source_path = Path(os.path.join(self.root_folder, version))
        target_path = Path(os.path.join(self.root_folder, nice_name))
        source_path.rename(target_path)

        # Register .blend extension
        if self.parent.settings.value('is_register_blend', type=bool):
            if self.platform == 'Windows':
                b3d_exe = target_path / "blender.exe"
                subprocess.call([str(b3d_exe), "-r"], creationflags=CREATE_NO_WINDOW,
                                shell=True, stdout=PIPE, stderr=STDOUT, stdin=DEVNULL)
            elif self.platform == 'Linux':
                pass
                # TODO Linux has different file association method?
                # b3d_exe = target_path / "blender"
                # subprocess.call([str(b3d_exe), "-r"],
                # shell=True, stdout=PIPE, stderr=STDOUT, stdin=DEVNULL)

        self.finished.emit(nice_name)

    def stop(self):
        self.is_running = False

import os
import tempfile
import logging
import urllib
import docker
import subprocess

from .command import Command

dockerfile_template = """
RUN mkdir -p /work/generate/appdir/

ARG USE_PRELOADER=false
ARG PRELOADER_TAR
COPY [ "${PRELOADER_TAR}", "/work/generate/preloader.tar" ]

ARG APPDIR
ADD [ "${APPDIR}", "/work/generate/appdir/" ]

ARG OUTPUT_NAME
RUN mksquashfs /work/generate/appdir/ /work/generate/app.sqfs && \\
    echo -n "objcopy " > /tmp/build.sh && \\
    echo -n " --add-section .aimg_sqfs=/work/generate/app.sqfs --set-section-flags .aimg_sqfs=noload,readonly " >> /tmp/build.sh && \\
    ( [ "${USE_PRELOADER}" = "true" ] && echo -n " --add-section .aimg_pre_tar=/work/generate/preloader.tar --set-section-flags .aimg_pre_tar=noload,readonly --set-section-alignment .aimg_pre_tar=4096 " >> /tmp/build.sh || true ) && \\
    echo -n " ${APPIMAGE_RUNTIME_FILE} /work/generate/${OUTPUT_NAME}" >> /tmp/build.sh && \\
    chmod +x /tmp/build.sh && \\
    cat /tmp/build.sh && echo && \\
    /tmp/build.sh

FROM scratch
ARG OUTPUT_NAME
COPY --from=generate_appimage "/work/generate/${OUTPUT_NAME}" "/${OUTPUT_NAME}"
"""

class AppImageDockerBuilderCommand(Command):
    def __init__(self, app_dir, target_file):
        super().__init__("appimagekit_docker")

        self.app_dir = app_dir
        self.runtime_file = None
        self.update_information = None
        self.guess_update_information = False
        self.sign_key = None
        self.target_file = target_file
        self.target_name = os.path.basename(target_file)
        self.target_arch = None
        self.preloader_tar = None

        self.dummy_file = self.app_dir + "/.empty"

        self.docker_client = docker.from_env()

    def run(self):
        logging.info("Generating AppImage from %s" % self.app_dir)

        if not self.preloader_tar:
            open(self.dummy_file, 'w').close()

        try:
            base_image = "ghcr.io/jclab-joseph/appimagekit:tag-13jclab02-xx" + self.target_arch
            pulled_image = self.docker_client.images.pull(base_image)
            dockerfile = self._generate_dockerfile_1(base_image)
        except:
            dockerfile = self._generate_dockerfile_2("https://raw.githubusercontent.com/jclab-joseph/AppImageKit/master/linux.Dockerfile")

        command = self._generate_command(dockerfile)

        if self.target_arch:
            self.env["ARCH"] = self.target_arch

        self._run(command)
        if self.return_code != 0:
            logging.error("AppImage generation failed")
        else:
            logging.info("AppImage created successfully")

        os.unlink(dockerfile)

    def _generate_dockerfile_1(self, base_image):
        content = "FROM " + base_image + "\n" + dockerfile_template
        file = tempfile.mktemp(".Dockerfile", ".tmp ", os.getcwd())
        with open(file, 'w') as f:
            f.write(content)
        return file

    def _generate_dockerfile_2(self, base_file_url):
        request = urllib.request or urllib
        content = request.urlopen(base_file_url).read().decode('utf-8')
        content = content.replace("\n# APPIMAGE_BUILDER_IMAGE", " as generate_appimage")
        content += "\n" + dockerfile_template
        file = tempfile.mktemp(".Dockerfile")
        with open(file, 'w') as f:
            f.write(content)
        return file

    def _generate_command(self, dockerfile):
        command = ["docker", "buildx", "build"]

        if self.preloader_tar:
            command.extend(["--build-arg", "USE_PRELOADER=true"])
            command.extend(["--build-arg", "PRELOADER_TAR=" + self.preloader_tar])
        else:
            command.extend(["--build-arg", "PRELOADER_TAR=" + self.dummy_file])

        command.extend(["--build-arg", "OUTPUT_NAME=" + self.target_name])
        command.extend(["-o type=local,dest=./"])
        command.extend([".", "-f", dockerfile])
        print(command)
        exit (1)

        # command = ["appimagetool"]
        # if self.runtime_file:
        #     command.extend(["--runtime-file", self.runtime_file])
        #
        # if self.sign_key:
        #     command.extend(["--sign", "--sign-key", self.sign_key])
        #
        # if self.update_information:
        #     command.extend(["--updateinformation", self.update_information])
        #
        # if self.guess_update_information:
        #     command.extend(["--guess"])
        #
        # command.extend([self.app_dir, self.target_file])
        return command

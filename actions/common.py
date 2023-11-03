# Copyright 1999 - 2023. Plesk International GmbH. All rights reserved.
import os
import subprocess
import sys
import time
import typing

from common import action, files, motd, plesk, util


class FixNamedConfig(action.ActiveAction):
    def __init__(self):
        self.name = "fix named configuration"
        self.user_options_path = "/etc/named-user-options.conf"
        self.chrooted_file_path = "/var/named/chroot/etc/named-user-options.conf"

    def _is_required(self) -> bool:
        return os.path.exists(self.chrooted_file_path)

    def _prepare_action(self) -> None:
        if not os.path.exists(self.user_options_path):
            os.symlink(self.chrooted_file_path, self.user_options_path)

        if os.path.getsize(self.chrooted_file_path) == 0:
            with open(self.chrooted_file_path, "w") as f:
                f.write("# centos2alma workaround commentary")

    def _post_action(self) -> None:
        if os.path.exists(self.user_options_path):
            os.unlink(self.user_options_path)

        with open(self.chrooted_file_path, "r") as f:
            if f.read() == "# centos2alma workaround commentary":
                os.unlink(self.chrooted_file_path)
                with open(self.chrooted_file_path, "w") as _:
                    pass

    def _revert_action(self) -> None:
        if os.path.exists(self.user_options_path):
            os.unlink(self.user_options_path)


class DisableSuspiciousKernelModules(action.ActiveAction):
    def __init__(self):
        self.name = "rule suspicious kernel modules"
        self.suspicious_modules = ["pata_acpi", "btrfs", "floppy"]
        self.modules_konfig_path = "/etc/modprobe.d/pataacpibl.conf"

    def _get_enabled_modules(self, lookup_modules: typing.List[str]) -> typing.List[str]:
        modules = []
        modules_list = subprocess.check_output(["/usr/sbin/lsmod"], universal_newlines=True).splitlines()
        for line in modules_list:
            module_name = line[:line.find(' ')]
            if module_name in lookup_modules:
                modules.append(module_name)
        return modules

    def _prepare_action(self) -> None:
        with open(self.modules_konfig_path, "a") as kern_mods_config:
            for suspicious_module in self.suspicious_modules:
                kern_mods_config.write("blacklist {module}\n".format(module=suspicious_module))

        for enabled_modules in self._get_enabled_modules(self.suspicious_modules):
            util.logged_check_call(["/usr/sbin/rmmod", enabled_modules])

    def _post_action(self) -> None:
        for module in self.suspicious_modules:
            files.replace_string(self.modules_konfig_path, "blacklist " + module, "")

    def _revert_action(self) -> None:
        if not os.path.exists(self.modules_konfig_path):
            return

        for module in self.suspicious_modules:
            files.replace_string(self.modules_konfig_path, "blacklist " + module, "")


class RuleSelinux(action.ActiveAction):
    def __init__(self):
        self.name = "rule selinux status"
        self.selinux_config = "/etc/selinux/config"
        self.getenforce_cmd = "/usr/sbin/getenforce"

    def _is_required(self) -> bool:
        if not os.path.exists(self.selinux_config) or not os.path.exists(self.getenforce_cmd):
            return False

        return subprocess.check_output([self.getenforce_cmd], universal_newlines=True).strip() == "Enforcing"

    def _prepare_action(self) -> None:
        files.replace_string(self.selinux_config, "SELINUX=enforcing", "SELINUX=permissive")

    def _post_action(self) -> None:
        files.replace_string(self.selinux_config, "SELINUX=permissive", "SELINUX=enforcing")

    def _revert_action(self) -> None:
        files.replace_string(self.selinux_config, "SELINUX=permissive", "SELINUX=enforcing")


class AddFinishSshLoginMessage(action.ActiveAction):
    def __init__(self):
        self.name = "add finish ssh login message"
        self.finish_message = """
The server has been converted to AlmaLinux 8.
"""

    def _prepare_action(self) -> None:
        pass

    def _post_action(self) -> None:
        motd.add_finish_ssh_login_message(self.finish_message)
        motd.publish_finish_ssh_login_message()

    def _revert_action(self) -> None:
        pass


class AddInProgressSshLoginMessage(action.ActiveAction):
    def __init__(self):
        self.name = "add in progress ssh login message"
        path_to_script = os.path.abspath(sys.argv[0])
        self.in_progress_message = f"""
===============================================================================
Message from the Plesk centos2alma tool:
The server is being converted to AlmaLinux 8. Please wait.
To see the current conversion status, run the '{path_to_script} --status' command.
To monitor the conversion progress in real time, run the '{path_to_script} --monitor' command.
===============================================================================
"""

    def _prepare_action(self) -> None:
        motd.add_inprogress_ssh_login_message(self.in_progress_message)

    def _post_action(self) -> None:
        pass

    def _revert_action(self) -> None:
        motd.restore_ssh_login_message()


class DisablePleskSshBanner(action.ActiveAction):
    def __init__(self):
        self.name = "disable plesk ssh banner"
        self.banner_command_path = "/root/.plesk_banner"

    def _prepare_action(self) -> None:
        if os.path.exists(self.banner_command_path):
            files.backup_file(self.banner_command_path)
            os.unlink(self.banner_command_path)

    def _post_action(self) -> None:
        files.restore_file_from_backup(self.banner_command_path)

    def _revert_action(self) -> None:
        files.restore_file_from_backup(self.banner_command_path)


class PreRebootPause(action.ActiveAction):
    def __init__(self, reboot_message: str, pause_time: int = 45):
        self.name = "pause before reboot"
        self.pause_time = pause_time
        self.message = reboot_message

    def _prepare_action(self) -> None:
        print(self.message)
        time.sleep(self.pause_time)

    def _post_action(self) -> None:
        pass

    def _revert_action(self) -> None:
        pass


class HandleConversionStatus(action.ActiveAction):
    def __init__(self):
        self.name = "prepare and send conversion status"

    def _prepare_action(self) -> None:
        plesk.prepare_conversion_flag()

    def _post_action(self) -> None:
        plesk.send_conversion_status(True)

    def _revert_action(self) -> None:
        plesk.remove_conversion_flag()


class FixSyslogLogrotateConfig(action.ActiveAction):
    def __init__(self):
        self.name = "fix logrotate config for rsyslog"
        self.config_path = "/etc/logrotate.d/syslog"
        self.right_logrotate_config = """
/var/log/cron
/var/log/messages
/var/log/secure
/var/log/spooler
{
    missingok
    sharedscripts
    postrotate
        /usr/bin/systemctl kill -s HUP rsyslog.service >/dev/null 2>&1 || true
    endscript
}
"""

    def _prepare_action(self):
        pass

    def _post_action(self):
        files.backup_file(self.config_path)
        with open(self.config_path, "w") as f:
            f.write(self.right_logrotate_config)

    def _revert_action(self):
        pass

#! /usr/bin/env python

from ansible.module_utils.basic import AnsibleModule
from subprocess import Popen, PIPE

ANSIBLE_METADATA = {
    "metadata_version": "1.0",
    "supported_by": "community",
    "status": ["preview"],
    "version": "1.0.0"
}

DOCUMENTATION = """
---
module: hdfs_file
short_description: Set attributes of files in the hadoop file system
description:
    - This module allows file/directory management.
    - It assert the status for a given path, like owner, group, mode.
version_added: "2.2"
author: Cedric KASSI from Antoine Pointeau (refactoring)
options:
    group:
        description:
            - Name of the group that should own the
            - file/directory, as would be fed to chown.
    mode:
        description:
            - Mode the file or directory should be. For those used to
            - /usr/bin/chmod remember that modes are actually octal numbers
            - (eg. 0644). Noe the this fonction will always set changed
            - due to CLI limitation (cannot get file mode)
    owner:
        description:
            - Name of the user that should own the
            - file/directory, as would be fed to chown.
    path:
        description:
            - The hdfs absolute path being managed
        required: true
        aliases:
            - dest
            - name
    recurse:
        description:
            - The module will recursively set the specified file
            - attributes (applies only to state=directory)
    kerberos_keytab:
        description:
            - kerberos keytab path
        required: false
    kerberos_principal:
        description:
            - kerberos principal
        required: false
    replication:
        description:
            - The replication factor of a file/directory, please
            - not that setting the replication on a directory is
            - always apply recursivly.
    state:
        description:
            - If `directory`, all immediate subdirectories will
            - be created if they do not exist, they will be created
            - with the supplied permissions.
            - If `file`, the file will NOT be created if it does not exist,
            - see the `hdfs_copy` module if you want that behavior.
            - If `absent`, directories will be recursively deleted,
            - and files will be unlinked. Note that `hdfs_file` will not fail
            - if the path does not exist as the state did not change.
            - If `touch`, an empty file will be created if the path does
            - not exist, while an existing file will receive updated file
            - access and modification times (directories stay untouch). Please
            - note that touch update file owner, group, mode and replication,
            - you should set this param explicitly to replace them.
        default: file
        choices:
            - directory
            - file
            - absent
            - touch
notes:
    - check_mode supported
"""

EXAMPLES = """

- name: Create folder
  hdfs_file:
    path: /tmp/myfolder
    state: directory
    owner: myuser
    group: mygroup
    mode: 0755

- name: Delete the folder
  hdfs_file:
    path: /tmp/myfolder
    state: absent

- name: Create file
  hdfs_file:
    path: /tmp/myfile
    kerberos_keytab: "/tmp/kerberos.keytab"
    kerberos_principal: "project/phadlxXX.haas.socgen@PHAD"
    state: touch

"""

# --------------------------------------------------------------------------- #
# ----------------------------------------------------------------- HdfsUtils #
# --------------------------------------------------------------------------- #

"""
Catchable class to handle the Exception of this bundle
"""


class HdfsUtilsError(Exception):
    pass


# --------------------------------------------------------------------------- #
# ------------------------------------------------------------ HdfsContextCli #
# --------------------------------------------------------------------------- #


"""
This module give an hdfs context using CLI to manage the file system.
All Exception will be raised with the class `HdfsUtilsError` but
the common usage is to catch `HdfsUtilsError`.

Public methods short descriptions:
- chmod: change file/directory right mode
- chown: change file/directory owner/group
- mkdir: create a directory
- remove: delete a file/directory

- setrep: set a file/directory replication factor
- stats: get informations about a file/directory
- touch: create file or update file access
"""


class HdfsContextCli:
    def __init__(self, command="/bin/hdfs"):
        """
        The param :command: allow to change the CLI path, it's not common
        to set this parameter.
        """
        self.cmd = command

    def __execute_hdfs_commands__(self, command, keytab, principal, error_msg, skip_error=False):
        if keytab is not None and principal is not None:
            kerberos_command = [
                "/bin/kinit",
                "-t",
                keytab,
                "-k",
                principal,
            ]
            kerberos_error_msg = "Failed to init keytab with principal :  %s"
            self.__execute_command__(kerberos_command, kerberos_error_msg)
        return self.__execute_command__(command, error_msg, skip_error=skip_error)

    def __execute_command__(self, command, error_msg, skip_error=False):

        proc = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        out, err = proc.communicate()
        proc_wait = proc.wait()
        if proc_wait is not 0 and skip_error is False:
            raise HdfsUtilsError(error_msg % err)
        return out, err, proc_wait


    def chmod(self, path, mode, keytab, principal, recurse=None):
        """
        Change the :mode: of the given :path:. The param :mode: needs to
        be a string representation of an octal number (eg. "0744")
        """
        cmd = [self.cmd, "dfs", "-chmod", mode, path]
        if recurse:
            cmd.insert(3, "-R")
        error_msg = "subprocess chmod stderr: %s"
        self.__execute_hdfs_commands__(cmd, keytab, principal, error_msg)
        return (self)

    def chown(self, path, keytab, principal, owner=None, group=None, recurse=None):
        """
        Change the :owner: and/or :group: for the given :path:. The param
        :recurse: apply the changes for all subfiles and subfolders inside
        the give :path:. (should be a directory)
        """
        target = owner if owner else "" + ":" + group if group else ""
        cmd = [self.cmd, "dfs", "-chown", target, path]
        if recurse:
            cmd.insert(3, "-R")
        error_msg = "subprocess chown stderr: %s"
        self.__execute_hdfs_commands__(cmd, keytab, principal, error_msg)
        return (self)

    def mkdir(self, path, keytab, principal, parent=False):
        """
        Create the directory pointed by :path:, the param :parent: defines
        if immediate subdirectories should be created too. This method
        raises an HdfsUtilsError if the command failed.
        """
        cmd = [self.cmd, "dfs", "-mkdir", path]
        if parent:
            cmd.insert(3, "-p")
        error_msg = "subprocess mkdir stderr: %s"
        self.__execute_hdfs_commands__(cmd, keytab, principal, error_msg)
        return (self)

    def remove(self, path, keytab, principal, recurse=False):
        """
        Remove the file/directory pointed by :path:, the params :recurse:
        allows to force delete directories and its content. This method
        raises an HdfsUtilsError if the command failed.
        """
        cmd = [self.cmd, "dfs", "-rm", path]
        if recurse:
            cmd.insert(3, "-r")
        error_msg = "subprocess rm stderr: %s"
        self.__execute_hdfs_commands__(cmd, keytab, principal, error_msg)
        return (self)

    def setrep(self, path, keytab, principal, factor):
        """
        Set the expected replication factor of the given :path:. The param
        :factor: is expected to be a number. Please not that the CLI always
        apply the factor recursivly on directories.
        """
        cmd = [self.cmd, "dfs", "-setrep", factor, path]
        error_msg = "subprocess setrep stderr: %s"
        self.__execute_hdfs_commands__(cmd, keytab, principal, error_msg)
        return (self)

    def stats(self, path, keytab, principal):
        """
        Return a formatted dict that contains the status for the
        given :path:.
        """
        result = {
            "state": "absent",
            "owner": None,
            "group": None,
            "replication": None
        }
        cmd = [self.cmd, "dfs", "-stat", "%F[SEP]%u[SEP]%g[SEP]%r", path]
        error_msg = "subprocess stats stderr: %s"
        out, err, proc_wait = self.__execute_hdfs_commands__(cmd, keytab, principal, error_msg, skip_error=True)
        if proc_wait is not 0:  # Assume no such file or directory
            return (result)
        out = out.strip().split("[SEP]")
        out_order = ["state", "owner", "group", "replication"]
        for idx, key in enumerate(out_order):  # Fill the dict
            result[key] = out[idx]
        if result["state"] == "regular file":  # Normalize file string
            result["state"] = "file"
        result["replication"] = int(result["replication"])
        return (result)

    def touch(self, path, keytab, principal):
        """
        Create a file at the given :path:, if the file already exist it
        updates file access and modification times. This method raises
        an HdfsUtilsError if the command failed.
        """
        cmd = [self.cmd, "dfs", "-touchz", path]
        error_msg = "subprocess rm touchz: %s"
        self.__execute_hdfs_commands__(cmd, keytab, principal, error_msg)
        return (self)


# --------------------------------------------------------------------------- #
# ------------------------------------------------------------ HdfsContextLib #
# --------------------------------------------------------------------------- #


"""
This module give an hdfs context using library to manage the file system.
All Exception will be raised with the class `HdfsContextLibError` but
the common usage is to catch `HdfsUtilsError`.

Public methods short descriptions:
- mkdir: create a directory
- remove: delete a file/directory
- stats: get informations about a file/directory
- touch: create file or update file access
"""


# --------------------------------------------------------------------------- #
# ------------------------------------------------------------- HdfsCheckMode #
# --------------------------------------------------------------------------- #

def build_module():
    argument_spec = dict(
        group=dict(default=None, required=False),
        mode=dict(default=None, required=False),
        owner=dict(default=None, required=False),
        path=dict(aliases=["dest", "name"], required=True),
        recurse=dict(default=None, required=False),
        replication=dict(default=None, required=False),
        kerberos_keytab=dict(default=None, required=False),
        kerberos_principal=dict(default=None, required=False),
        state=dict(
            default="file", required=False,
            choices=["file", "directory", "touch", "absent"]
        ),
    )
    mutually_exclusive = []
    module = AnsibleModule(
        argument_spec=argument_spec,
        mutually_exclusive=mutually_exclusive,
        supports_check_mode=True
    )
    return (module)


def resolv_states(module, params, context, status):
    old = status["state"]
    new = params["state"]
    try:
        if old == "absent" and new == "file":
            module.fail_json(msg="no such file, to create new file use state 'touch' instead of 'file'")
        elif old == "absent" and new == "directory":
            context.mkdir(params["path"], params["kerberos_keytab"], params["kerberos_principal"], parent=True)
        elif new == "touch" and old in ["absent", "file"]:
            context.touch(params["path"], params["kerberos_keytab"], params["kerberos_principal"])
        elif new == "absent" and old == "file":
            context.remove(params["path"], params["kerberos_keytab"], params["kerberos_principal"])
        elif new == "absent" and old == "directory":
            context.remove(params["path"], params["kerberos_keytab"], params["kerberos_principal"], recurse=True)
        else:
            module.fail_json(msg="unsupported state convert '%s' -> '%s'" % (old, new))
    except HdfsUtilsError as e:
        module.fail_json(msg=e)
    return True


def should_modify(status, params, value):
    if params[value] is None:
        return False
    if params["state"] == "touch":
        return True
    if str(status[value]) == str(params[value]):
        return False
    return True


def main():
    module = build_module()
    params = module.params
    changed = False

    context = HdfsContextCli()

    status = context.stats(params["path"], params["kerberos_keytab"], params["kerberos_principal"])
    # STATE
    if status["state"] != params["state"]:
        changed = True
        resolv_states(module, params, context, status)
    if params["state"] == "absent":
        module.exit_json(changed=changed)
    # OWNER
    if should_modify(status, params, "owner"):
        changed = True
        context.chown(params["path"], params["kerberos_keytab"], params["kerberos_principal"], owner=params["owner"], recurse=params["recurse"])
    # GROUP
    if should_modify(status, params, "group"):
        changed = True
        context.chown(params["path"], params["kerberos_keytab"], params["kerberos_principal"], group=params["group"], recurse=params["recurse"])
    # REPLICATION
    if should_modify(status, params, "replication"):
        changed = True
        context.setrep(params["path"], params["kerberos_keytab"], params["kerberos_principal"], params["replication"])
    # MODE
    if params["mode"] is not None:
        changed = True
        context.chmod(params["path"], params["kerberos_keytab"], params["kerberos_principal"], params["mode"], recurse=params["recurse"])

    module.exit_json(changed=changed)


if __name__ == "__main__":
    main()

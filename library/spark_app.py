#! /usr/bin/env python
# -*- coding: utf-8 -*-

from ansible.module_utils.basic import AnsibleModule
from subprocess import Popen, PIPE
import json
import re


ANSIBLE_METADATA = {
    "metadata_version": "1.0",
    "supported_by": "community",
    "status": ["preview"],
    "version": "1.0.0"
}

DOCUMENTATION = """
---
module: spark_app
short_description: Set attributes of files in the hadoop file system
description:
    - This module allows file/directory management.
    - It assert the status for a given path, like owner, group, mode.
version_added: "1.0"
author: Raianate KISSIAMOI
options:
    app_name:
        description:
            - The application given name
        required: true
    spark_class:
        description:
            - Spark application Class
        required: false // true for start operation
        
    master_url:
        description:
            - The application master url
        required: true
        
    queue:
        description:
            - The YARN queue to submit // only if master_url == yarn
        required: false
        
    mode:
        description:
            - The application deploy mode 
        choices:
            - client
            - cluster
        default: client
        
    extra_option:
        description:
            - Other spark parameter that are not specified 
        required: false    
            
    application_jar_path:
        description:
            - The application jar path
        required: false // true for start operation
        
    param_after_submit:
        description:
            - The parameter specified in application code
        required: false
        
    server:
        description:
            - The server in which the application has been deployed
        required: false // true for stop operation
        
     kerberos_keytab:
        description:
            - kerberos keytab path
        required: false

    kerberos_principal:
        description:
            - kerberos principal
        required: false
        
    state:
        description:
            - If `present`, will submit spark app
            - If `absent`, will stop spark app
        choices:
            - present
            - absent
        default: present
            
    
"""

EXAMPLES = """

- name: Submit spark app
  spark_app:
    name: "my spark application"
    spark_class: "My.Appli.Class"
    master_url: "yarn"
    queue: "BDDF"
    mode: "cluster"
    extras_option:
        - "--driver-memory 4g"
        - "--driver-cores 4"
    application_jar: "/complete/path/with/jar/name.jar"
    kerberos_keytab: "/tmp/kerberos.keytab"
    kerberos_principal: "project/phadlxXX.haas.socgen@PHAD"
    state: present

- name: Stop spark app
  spark_app:
    master_url: "local"
    name: "my spark application"
    server: "http://dhadlx111.haas.socgen:4040/api/v1/applications"
    kerberos_keytab: "/tmp/kerberos.keytab"
    kerberos_principal: "project/phadlxXX.haas.socgen@PHAD"
    state: absent

"""

# --------------------------------------------------------------------------- #
# ----------------------------------------------------------------- sparkUtils #
# --------------------------------------------------------------------------- #

"""
Catchable class to handle the Exception of this bundle
"""


class sparkUtilsError(Exception):
    pass


# --------------------------------------------------------------------------- #
# ------------------------------------------------------------ sparkContextCli #
# --------------------------------------------------------------------------- #


"""
This module give an spark context using CLI/curl to manage spark app.
All Exception will be raised with the class `sparkUtilsError` but
the common usage is to catch `sparkUtilsError`.

Public methods short descriptions:
- spark_app_exist: return application id if exist
- spark_app_stop: stop spark job
- spark_app_submit: submit spark job

- __query_spark_api__: query spark api
- __execute_command__: execute unit command cli
"""

'''

'''


class sparkContextCli:
    def __init__(self, command="/bin/curl"):
        """
        The param :command: allow to change the CLI path, it's not common
        to set this parameter.
        """
        self.cmd = command

    def __execute_command__(self, command, error_msg):

        proc = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        out, err = proc.communicate()
        if proc.wait() is not 0:
            raise sparkUtilsError(error_msg % err)
        return out, err

    def __query_spark_api__(self, query, keytab, principal, error_msg):
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
        return self.__execute_command__(query, error_msg)

    def spark_app_submit(self, name, spark_class, master_url, queue, mode, memory, number, cores, extra_option,
                         application_jar_path, params_after_submit, keytab, principal):

        """
        Check if an spark app exist
        """

        cmd = [
            "/usr/bin/spark-submit",
            "--name",
            name,
            "--class",
            spark_class,
            "--master",
            master_url,
            "--queue",
            queue,
            "--deploy-mode",
            mode,
            "--executor-memory",
            memory,
            "--num-executors",
            number,
            "--total-executor-cores",
            cores
            ]

        if extra_option != []:
            for option in extra_option:
                tab_option = option.split(" ")
                for opt in tab_option:
                    cmd.append(opt)


        cmd.append(application_jar_path)

        if params_after_submit != []:
           for params in params_after_submit:
               cmd.append(params)

        error_msg = "subprocess submit spark application stderr : %s"
        out, err = self.__query_spark_api__(cmd, keytab, principal, error_msg)
        return [dict(out=out, err=err)]

    def spark_app_exist(self, master, name, server, queue, keytab, principal):
        """
        Check if an spark app exist // to modify
        """
        app_id = None
        if master == "yarn":

            # request_url = "{0}/v1/cluster/apps?states=RUNNING&applicationTypes=SPARK&user={1}".format(server, ,user_amd)
            request_url = "{0}/ws/v1/cluster/apps?states=RUNNING&applicationTypes=SPARK&queue={1}".format(server, queue)

            cmd = [
                self.cmd,
                "-k",
                "--negotiate",
                "-u",
                ":",
                request_url
            ]
            error_msg = "subprocess check spark stderr: %s"
            retry = 0
            try:
                for retry in range(1,4):
                    out, err = self.__query_spark_api__(cmd, keytab, principal, error_msg)
                    json_content = json.loads(out)
                    if json_content["apps"] is not None:
                        for appli in json_content["apps"]["app"]:
                            if appli["name"] == name:
                                app_id = appli["id"]
                    return app_id
            except ValueError as e:
                print e
                retry +=1
                if retry == 3:
                    pass
            return app_id

        elif re.match("^local.", master):

            request_url = "{0}/api/v1/applications".format(server)

            cmd = [
                self.cmd,
                "--negotiate",
                "-u",
                ":",
                request_url
            ]
            error_msg = "subprocess check spark stderr: %s"

            try:
                for retry in range(1,4):
                    out, err = self.__query_spark_api__(cmd, keytab, principal, error_msg)
                    json_content = json.loads(out)
                    for appli in json_content:
                        if appli["name"] == name:
                            app_id = appli["id"]
                    return app_id
            except ValueError as e:
                print e
                retry +=1
                if retry == 3:
                    pass
            return app_id


    def spark_app_stop(self, master, app_id, keytab, principal):
        """
        Stop spark app
        """

        cmd = []
        if app_id is not None:
            if master == "yarn":
                cmd = [
                    "/usr/bin/yarn",
                    "application",
                    "-kill",
                    app_id
                ]
            if re.match("^local.", master):

                cmd = [
                    "/usr/bin/spark-submit",
                    "--kill",
                    app_id
                ]
            else:
                print ("Error, this application deploy master is not supported. Please contact your referred DevOps")

            error_msg = "subprocess stop spark stderr: %s"
            out, err = self.__query_spark_api__(cmd, keytab, principal, error_msg)
            return [dict(out=out, err=err)]
        return None


# --------------------------------------------------------------------------- #
# ------------------------------------------------------------ sparkContextLib #
# --------------------------------------------------------------------------- #


"""
This module give an spark context using library to manage the spark app.
All Exception will be raised with the class `sparkContextLibError` but
the common usage is to catch `sparkUtilsError`.

Public methods short descriptions:
- spark_app_exist: return app_id if exist
- spark_app_stop: kill spark app
- spark_app_submit: submit spark app
"""


def build_module():
    argument_spec = dict(
        app_name=dict(default=None, required=True),
        spark_class=dict(default=None, required=False),
        master_url=dict(default=None, required=True),
        queue=dict(default=None, required=False),
        mode=dict(
            default="cluster",
            choices=["cluster", "client"],
            required=False
        ),
        memory=dict(default=None, required=False),
        number=dict(default=None, required=False),
        cores=dict(default=None, required=False),
        extra_option=dict(type='list', default=[], required=False),
        application_jar_path=dict(type='path', default=None, required=False),
        param_after_submit=dict(type='list', default=[], required=False),
        #server=dict(default="http://dhadlx103.haas.socgen:8088/", required=False),
        server=dict(required=True),
        kerberos_keytab=dict(default=None, required=False),
        kerberos_principal=dict(default=None, required=False),
        state=dict(
            default="present", required=False,
            choices=["present", "absent"]
        ),
    )
    mutually_exclusive = []
    module = AnsibleModule(
        argument_spec=argument_spec,
        mutually_exclusive=mutually_exclusive,
        supports_check_mode=False,
        required_if=[
            ["state", "present", ["spark_class", "application_jar_path"]],
            ["state", "absent", ["server", "app_name"]]
        ]
    )
    return (module)


def main():
    module = build_module()
    params = module.params
    changed = False
    context = sparkContextCli()
    results = []
    app_id = context.spark_app_exist(
        params["master_url"],
        params["app_name"],
        params["server"],
        params["queue"],
        params["kerberos_keytab"],
        params["kerberos_principal"]
    )

    print "APP_ID %s" %app_id
    if params["state"] == "present" and app_id is None:
        changed = True

        results = context.spark_app_submit(
            params["app_name"],
            params["spark_class"],
            params["master_url"],
            params["queue"],
            params["mode"],
            params["memory"],
            params["number"],
            params["cores"],
            params["extra_option"],
            params["application_jar_path"],
            params["param_after_submit"],
            params["kerberos_keytab"],
            params["kerberos_principal"]
        )


    if params["state"] == "absent" and app_id is not None:
        changed = True
        results = context.spark_app_stop(
            params["master_url"],
            app_id,
            params["kerberos_keytab"],
            params["kerberos_principal"]
        )

    module.exit_json(changed=changed, results=results)


if __name__ == "__main__":
    main()

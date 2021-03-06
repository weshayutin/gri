#!/usr/bin/env python
# -*- coding: utf-8 -*-
from blessings import Terminal
from urllib.parse import urlparse
import click
import datetime
import json
import logging
import netrc
import os
import re
import requests
import sys

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse
import yaml
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

# ABANDON_MSG = ("\"This review is > 90 days without comment or update."
#               " We are abandoning this for now. Feel free to reactivate the review"
#               " by pressing the restore button and contacting the reviewers and ensure"
#               " you address their concerns. For more details check policy"
#               " https://specs.openstack.org/openstack/tripleo-specs/specs/policy/patch-abandonment.html\"")

ABANDON_MSG = (
    "https://specs.openstack.org/openstack/tripleo-specs/specs/policy/patch-abandonment.html")

# Used only to force outdated Digest auth for servers not using standard auth
KNOWN_SERVERS = {
    "https://review.opendev.org/": {"auth": HTTPDigestAuth},
    "https://review.rdoproject.org/": {"auth": HTTPDigestAuth},
    "https://code.engineering.redhat.com/gerrit/": {"auth": HTTPDigestAuth},
    "verify": False,
}
term = Terminal()

LOG = logging.getLogger(__name__)
time_now = datetime.datetime.now()


def link(url, name):
    return "\033]8;;{}\033\\{}\033]8;;\033\\".format(url, name)


class Label(object):
    def __init__(self, name, data):
        self.name = name
        self.abbr = re.sub("[^A-Z]", "", name)
        self.value = 0

        if data.get("blocking", False):
            self.value += -2
        if data.get("approved", False):
            self.value += 2
        if data.get("recommended", False):
            self.value += 1
        if data.get("disliked", False):
            self.value += -1
        if data.get("rejected", False):
            self.value += -1
        if data.get("optional", False):
            self.value = 1
        for unknown in set(data.keys()) - set(
            ["blocking", "approved", "recommended",
                "disliked", "rejected", "value", "optional"]
        ):
            LOG.warning("Found unknown label field %s: %s" %
                        (unknown, data.get(unknown)))

    def __repr__(self):
        msg = self.abbr + ":" + str(self.value)
        if self.value < 0:
            msg = term.red(msg)
        elif self.value == 0:
            msg = term.yellow(msg)
        elif self.value > 0:
            msg = term.green(msg)
        return msg


class GerritServer(object):
    def __init__(self, url, name=None):
        self.url = url
        self.name = name
        parsed_uri = urlparse(url)
        if not name:
            self.name = parsed_uri.netloc
        self.auth_class = HTTPBasicAuth

        # name is only used as an acronym
        self.__session = requests.Session()

        if self.url in KNOWN_SERVERS:
            self.auth_class = KNOWN_SERVERS[url]["auth"]
            self.__session.verify = KNOWN_SERVERS[url].get("verify", True)

        # workaround for netrc error: OSError("Could not find .netrc: $HOME is not set")
        if "HOME" not in os.environ:
            os.environ["HOME"] = os.path.expanduser("~")

        token = netrc.netrc().authenticators(parsed_uri.netloc)
        if not token:
            raise SystemError(
                "Unable to load credentials for %s from ~/.netrc file, add them dear human!", url
            )
        self.__session.auth = self.auth_class(token[0], token[2])

        self.__session.headers.update(
            {"Content-Type": "application/json;charset=UTF-8",
                "Access-Control-Allow-Origin": "*"}
        )

    def query(self, query=None, user=None, project=None):
        query_map = {
            None: r"a/changes/?q=owner:self%20status:open",
            "incoming": r"a/changes/?q=reviewer:self%20status:open",  # noqa
            "user": r"a/changes/?q=owner:" + str(user) + "%20status:open",
            "merged_today": r"a/changes/?q=status:merged%20tripleo%20age:0days",
            "project": r"a/changes/?q=project:" + str(project) + "%20status:open",
        }
        query = self.url + query_map[query] + "&o=LABELS&o=COMMIT_FOOTERS"
        # %20NOT%20label:Code-Review>=0,self
        return parsed(self.__session.get(query))


class CR:
    def __init__(self, data, server):
        self.data = data
        self.server = server
        self.score = 1.0

        LOG.debug(data)

        if "topic" not in data:
            self.topic = ""
        else:
            self.topic = data["topic"]

        self.is_wip = re.compile(
            "^\\[?(WIP|DNM|POC).+$", re.IGNORECASE).match(self.subject)
        self.url = "{}#/c/{}/".format(self.server.url, self.number)

        self.labels = {}
        for label_name, label_data in data.get("labels", {}).items():
            label = Label(label_name, label_data)
            self.labels[label_name] = label
            if label.abbr == "W":
                self.score += label.value * 20
            if label.abbr == "CR":
                self.score += label.value * 10
            if label.abbr == "V":
                self.score += label.value * 5
                if label.value == 0:
                    self.score -= 100
        if self.starred:
            self.score += 10

        # We just want to keep wip changes in the same are ~0..1 score.
        if self.is_wip:
            self.score /= 100

    def __repr__(self):
        return str(self.number)

    def __getattr__(self, name):
        if name in self.data:
            return self.data[name]
        elif name == "number":
            return self.data["_number"]

    def short_project(self):
        return re.search("([^/]*)$", self.project).group(0)

    def background(self):
        if self.is_wip:
            return 0
        gradient = [22, 58, 94, 130, 166, 196, 124]
        scores = [40, 15, 10, 0, -10, -20, -25]
        for i, s in enumerate(scores):
            if self.score > s:
                break
        return gradient[i]

    def __str__(self):

        prefix = "%s%s" % (u"⭐" if self.starred else "  ",
                           " " * (8 - len(str(self.number))))
        msg = term.on_color(self.background()) + prefix + \
            link(self.url, self.number) + term.normal

        m = ""
        if self.is_wip:
            m += " " + term.yellow(self.short_project())
        else:
            m += " " + term.bright_yellow(self.short_project())

        if self.branch != "master":
            m += term.bright_magenta(" [%s]" % self.branch)

        if self.is_wip:
            m += term.bright_black(": %s" % (self.subject))
        else:
            m += ": %s" % (self.subject)

        if self.topic:
            topic_url = "{}#/q/topic:{}+(status:open+OR+status:merged)".format(
                self.server.url, self.topic
            )
            m += term.blue(" " + link(topic_url, self.topic))

        if not self.mergeable:
            m += term.bright_red(" cannot-merge")

        for l in self.labels.values():
            if l.value:
                # we print only labels without 0 value
                m += " %s" % l
        time_cr_updated = datetime.datetime.strptime(
            self.updated[:-3], '%Y-%m-%d %H:%M:%S.%f')

        age = str((time_now - time_cr_updated).days)
        if int(age) > 60:
            m += term.yellow(" " + age + "_days_old")
        else:
            m += " " + age + "_days_old"

        msg += m + " %s" % self.score
        return msg

    def is_reviewed(self):
        return self.data["labels"]["Code-Review"]["value"] > 1

    def __lt__(self, other):
        return self.score >= other.score


class Config(dict):
    def __init__(self):
        self.update(self.load_config("~/.gertty.yaml"))

    def load_config(self, config_file):
        config_file = os.path.expanduser(config_file)
        with open(config_file, "r") as stream:
            try:
                return yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                LOG.error(exc)
                sys.exit(2)


class GRI(object):
    def __init__(self, query=None, server=None, user=None, project=None):
        self.cfg = Config()
        self.servers = []
        for s in self.cfg["servers"] if server is None else [self.cfg["servers"][int(server)]]:
            try:
                self.servers.append(GerritServer(url=s["url"], name=s["name"]))
            except SystemError as e:
                LOG.error(e)
        if not self.servers:
            sys.exit(1)

        self.reviews = list()
        for server in self.servers:

            for r in server.query(query=query, user=user, project=project):
                cr = CR(r, server)
                self.reviews.append(cr)

    def header(self):
        msg = "GRI using %s servers:" % len(self.servers)
        for s in self.servers:
            msg += " %s" % s.name
        return term.on_bright_black(msg)


def parsed(result):
    result.raise_for_status()

    if hasattr(result, "text") and result.text[:4] == ")]}'":
        return json.loads(result.text[5:])
    else:
        print("ERROR: %s " % (result.result_code))
        sys.exit(1)


@click.command()
@click.option("--abandon", "-a", default=False, help="abandon reviews with a score lower than 1 and greater than $abandon_age (default=90) days old", is_flag=True)
@click.option("--force_abandon", "-x", default=False, help="abandon regardless of the score, only use the age", is_flag=True)
@click.option("--debug", "-d", default=False, help="Debug mode", is_flag=True)
@click.option("--incoming", "-i", default=False, help="Incoming reviews (not mine)", is_flag=True)
@click.option("--merged_today", "-m", default=False, help="merged today in tripleo", is_flag=True)
@click.option("--server", "-s", default=None, help="[0,1,2] key in list of servers, Query a single server instead of all")
@click.option("--abandon_age", "-z", default=90, help="default=90, allow the abandon for reviews older than $abandon_age days")
@click.option("--user", "-u", default=None, help="if not self, pick a user to find patches")
@click.option("--project", "-p", default=None, type=str, help="specify a particular gerrit project to query")
@click.option("--print_csv", "-c", default=False, is_flag=True, help="print limited data in csv format for reports")
def main(debug, incoming, server, abandon, abandon_age, force_abandon, user, project, merged_today, print_csv=False):
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)-8s %(message)s")
    handler.setFormatter(formatter)
    LOG.addHandler(handler)
    # the score a cr must have by default in order to be abandoned
    abandon_score = 1

    # if force_abandon is true, set the score to any cr under a score of 300
    if force_abandon:
        abandon_score = 300

    # if --user is used set the query key to user
    # set the map to user
    if user:
        query = "user"
    elif incoming:
        query = "incoming"
    elif merged_today:
        query = "merged_today"
    elif project:
        query = "project"
    else:
        query = None
    if sys.version_info.major < 3:
        reload(sys)  # noqa
        sys.setdefaultencoding("utf8")

    if debug:
        LOG.setLevel(level=logging.DEBUG)
    # msg =""
    # gradient = [22, 58, 94, 130, 166, 196, 124]
    # for g in gradient:
    #     msg += term.on_color(g) + "A"
    # print(msg)
    # # return
    if user:
        gri = GRI(query="user", server=server, user=user)
    elif project:
        gri = GRI(query="project", server=server, project=project)
    else:
        gri = GRI(query=query, server=server)
    print(gri.header())
    cnt = 0
    for cr in sorted(gri.reviews):
        # msg = term.on_color(cr.background()) + str(cr)
        cr_last_updated = cr.data['updated']
        time_cr_updated = datetime.datetime.strptime(
            cr_last_updated[:-3], '%Y-%m-%d %H:%M:%S.%f')
        cr_age = time_now - time_cr_updated
        cr_updated_epoch = time_cr_updated.strftime('%s')

        if merged_today and int(cr_age.days) > 0:
            cnt -= 1
            continue
        if not print_csv:
            print(cr)
        else:
            print("merged,'{}','{}','{}','{}' '{}',{} {}".format(
                cr.project, cr.branch,
                cr.url, cr.subject,
                cr.url, cr_updated_epoch,
                cr_updated_epoch))
        if cr.score < abandon_score and abandon:
            if int(cr_age.days) > int(abandon_age) and query != "incoming":
                # shell out here because the using the api to abandon seems to be forbidden
                print("this review will now be abandoned")
                hostname = urlparse(cr.url).hostname
                cr_abandon = ("ssh -p 29418 " + gri.cfg['servers'][int(server)]['username']
                              + "@" + hostname + " gerrit review "
                              + str(cr.number) + ",1 --abandon --message " + ABANDON_MSG)
                print(cr_abandon)
                os.system(cr_abandon)
        LOG.debug(cr.data)
        cnt += 1
    print(term.bright_black("-- %d changes listed" % cnt))


if __name__ == "__main__":

    main()

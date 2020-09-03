# gri : Gerrit Reduced Interface

`gri`[¹](#f11) is a CLI tool that will list your open git reviews from multiple servers
in a way that makes easier to to identify which one need.

![screenshot](https://github.com/weshayutin/gri/blob/master/Screenshot%20from%202020-09-03%2010-39-13.png)

## Features
* multiple Gerrit servers
* change number and topics are clickable links
* draft/dnm/wip changes are grayed out
* automatically abandon review w/ score less than 1 and over 90 days old

## Wishlist

* Configurable Gerrit servers
* Sorting :: top ones should be those closer to be merged
* Grouping
* Caching
* Dependency graph based on zuul Depends-On
* Configurable query
* Include starred changes
* Zuul build status support
* top mode :: so it can auto-refresh and notify you of important changes

## Installing
```
git clone https://github.com/weshayutin/gri.git
cd gri
sudo python3 setup.py install

or in a local virtual environment

mkdir ~/virtualenv/python3
virtualenv -p /usr/bin/python3 ~/virtualenv/python3/
source ~/virtualenv/python3/bin/activate
git clone https://github.com/weshayutin/gri.git
cd gri
python3 setup.py install

now execute:
gri --help
```

## Usage
Currently the tool loads gerrit servers defined in [`~/.gertty.yaml`][1] but
uses credentials from `~/.netrc` file.

So use it just run `gli`, or `python -m gri`.

## Contributing
Are you missing a feature, just check if there is a bug open for it and add
a new one if not. Once done, you are welcomed to make a PR that implements
the missing change.

## Related tools
* [git-review][3] is the git extension for working with gerrit, where I am also
one of the core contributors.
* [GerTTY](https://github.com/openstack/gertty) is a very useful tui for gerrit
which inspired me but which presents one essential design limitation: it does
not work with multiple Gerrit servers.
* [Gerrit-View](https://github.com/Gruntfuggly/gerrit-view) is a vscode plugin
that can be installed from [Visual Studio Marketplace][2].

## Notes
1. <span id="f1"></span> The reality is that `gri` name comes from my attempt to
find a short namespace on pypi that was starting with g (from Gerrit) and
preferably sounds like `cli`, most were taken. You are welcomed to propose
better acronym expansions.

[1]: https://github.com/openstack/gertty/tree/master/examples
[2]: https://marketplace.visualstudio.com/items?itemName=Gruntfuggly.gerrit-view
[3]: https://docs.openstack.org/infra/git-review/

## Gerrit Servers with self signed certs
1. Find the cert in question, rpm -ql foo-internal-cert-install
2. sudo cp /etc/pki/tls/certs/newca.crt /usr/share/pki/ca-trust-source/anchors
3. update-ca-trust trust force-enable
4. update-ca-trust extract
5. Ensure you have the right url.. It could be https://hostname/gerrit or something like that

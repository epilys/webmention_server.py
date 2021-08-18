#
# webmention_server.py
#
# Copyright (C) 2021 - Emmanouil Pitsidianakis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import sys
import re
import argparse
import json
import http.server
import urllib.request
import urllib.parse
from urllib.parse import parse_qs
from html.parser import HTMLParser


def send_webmention(serverurl, source, target):
    links = webmention_discovery(serverurl)
    if len(links) == 0:
        print(f"{serverurl} has no webmention setup")
        return None
    ret = None
    for url in links:
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode({"source": source, "target": target}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            ret = str(response.status)
        if ret.startswith("2"):
            return ret
    return ret


def webmention_discovery(url):
    """Checks url for webmention endpoints.
    - First tries a HEAD request and looks at the HTTP response headers.
    - Then does a GET request and looks for webmention links in the body.
    """

    def to_absolute(root, url):
        return urllib.parse.urljoin(root, url)

    def parse_header_links(value):
        """Return a dict of parsed link headers proxies.
        i.e. Link: <http:/.../front.jpeg>; rel=front; type="image/jpeg",<http://.../back.jpeg>; rel=back;type="image/jpeg"
        Implementation taken from https://github.com/kennethreitz/requests/blob/f5dacf84468ab7e0631cc61a3f1431a32e3e143c/requests/utils.py#L580
        """

        links = []
        replace_chars = " '\""
        for val in re.split(", *<", value):
            try:
                url, params = val.split(";", 1)
            except ValueError:
                url, params = val, ""
            link = {}
            link["url"] = url.strip("<> '\"")
            for param in params.split(";"):
                try:
                    key, value = param.split("=")
                except ValueError:
                    break
                link[key.strip(replace_chars)] = value.strip(replace_chars)
            links.append(link)
        return links

    def check_link_header(req):
        print("checking response headers for Link header...")
        links = set()
        req.add_header("User-agent", "Webmention discovery/urllib+python3")
        with urllib.request.urlopen(req, timeout=3) as response:
            link_header = response.getheader("Link")
            if link_header is not None:
                for link in parse_header_links(link_header):
                    if "rel" in link and link["rel"] == "webmention":
                        print("found ", link["url"])
                        links.add(link["url"])
            body = response.read().decode("utf-8")
        return (links, body)

    urlparse = urllib.parse.urlparse(url, scheme="http")
    root = f"{urlparse.scheme}://{urlparse.netloc}"
    links = set()
    print("performing HEAD request...")
    req = urllib.request.Request(url, method="HEAD")
    links |= check_link_header(req)[0]
    if len(links) == 0:
        req = urllib.request.Request(url, method="GET")
        (get_links, response) = check_link_header(req)
        links |= get_links
        if len(links) == 0:
            links |= LinkFinder.extract(response)["webmention_links"]
    return [to_absolute(root, l) for l in links]


class LinkFinder(HTMLParser):
    """Parse an HTML document and return all <a> and <link> links.
    Returns:
    {
        "links": [str],
        "webmention_links": [str],
    }
    """

    links = set()
    webmention_links = set()

    def reset(self):
        self.links = set()
        self.webmention_links = set()
        super().reset()

    def handle_starttag(self, tag, attrs):
        if tag not in ["a", "link"]:
            return
        attrs = {a[0]: a[1] for a in attrs}
        if "rel" in attrs and attrs["rel"] == "webmention":
            if "href" in attrs:
                print("found", attrs["href"])
                self.webmention_links.add(attrs["href"])
        elif "href" in attrs:
            self.links.add(attrs["href"])

    def handle_endtag(self, tag):
        pass

    def handle_data(self, data):
        pass

    @staticmethod
    def extract(input_):
        print("searching HTML response for links...")
        linkparser = LinkFinder()
        linkparser.feed(input_)
        return {
            "links": linkparser.links,
            "webmention_links": linkparser.webmention_links,
        }


class WebmentionHandler(http.server.SimpleHTTPRequestHandler):
    def do_HEAD(self, *args, **kwargs):
        path = self.path.lstrip("/")
        target = None
        body = ""
        for s in self.server.config["sources"]:
            if path == s["source"]:
                target = s["target"]
        if not target:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain;charset=utf-8")
            body = "Not found."
            self.send_header("Content-Length", str(len(body)))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            body = f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8><title>{target}</title></head><body><a href="{target}">target</a>"""
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Link",
                f"<http://{self.server.server_address[0]}:{self.server.server_address[1]}>; rel=webmention",
            )
        self.end_headers()

    def do_GET(self, *args, **kwargs):
        path = self.path.lstrip("/")
        target = None
        body = ""
        for s in self.server.config["sources"]:
            if path == s["source"]:
                target = s["target"]
        if not target:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain;charset=utf-8")
            body = "Not found."
            self.send_header("Content-Length", str(len(body)))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            body = f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8><title>{target}</title></head><body><a href="{target}">target</a>"""
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(bytes(body, "utf-8"))

    def do_POST(self, *args, **kwargs):
        content_len = int(self.headers.get("Content-Length"))
        body = self.rfile.read(content_len).decode("utf-8")
        parsed = parse_qs(body)
        if "source" not in parsed or "target" not in parsed or len(parsed) != 2:
            self.send_response(400)
        else:
            if self.server.config["accept_all"]:
                self.send_response(202)
            else:
                path = self.path
                if path not in list(
                    map(lambda v: v["source"], self.server.config["sources"])
                ):
                    self.send_response(400)
                else:
                    self.send_response(202)
        self.end_headers()
        self.wfile.write(b"")


handler = WebmentionHandler


class WebmentionServer(http.server.HTTPServer):
    def __init__(self, config, *args, **kwargs):
        self.config = config
        super().__init__(*args, **kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Host dummy webmention server for testing."
    )
    parser.add_argument("PORT", type=int, default=8000, help="default port: 8000")
    parser.add_argument(
        "--accept-all", action="store_true", default=True, help="accept all targets."
    )
    parser.add_argument(
        "--sources",
        default=None,
        help="""JSON file with sources. Must be an array of dictionarys with two keys: source and target. Example:
[
  {
    "source":"",
    "target":"http://super.cool.domain.tld/post-about-something/"
  },
  {
    "source":"bookmarks",
    "target":"http://super.cool.domain.tld/post-about-something-else/"
  }
  ]

  This will serve two pages containing only the target links in order to allow verification of webmentions: The root page: "/" and "/bookmarks"
            """,
    )
    parser.add_argument(
        "--send-to",
        default=None,
        help="send webmentions to address before starting server, with targets from sources argument.",
    )

    args = parser.parse_args()
    print("Arguments:", args)
    if args.sources:
        with open(args.sources, "r") as s:
            sources = json.loads(s.read())
            for source in sources:
                if "source" not in source or "target" not in source or len(source) != 2:
                    print(
                        f"malformed entry in sources file: {source}. Entries must only have 'source' and 'target' set"
                    )
                    sys.exit(1)
    else:
        sources = None
    config = {
        "sources": sources if sources else [],
        "accept_all": args.accept_all,
    }

    with WebmentionServer(config, ("", args.PORT), handler) as httpd:
        if args.send_to:
            print(f"sending webmentions to {args.send_to}.")
            for s in config["sources"]:
                print(f" * webmentioning target {s['target']}.")
                result = send_webmention(
                    args.send_to,
                    f"""http://{httpd.server_address[0]}:{httpd.server_address[1]}/{s["source"]}""",
                    s["target"],
                )
                if result:
                    print(f" * {args.send_to} returned: {result}")

        print("serving at port", args.PORT)
        httpd.allow_reuse_address = True
        httpd.serve_forever()

import argparse
from threading import Lock
import subprocess
import logging

from twisted.internet import task
from twisted.internet.defer import DeferredList, Deferred
from twisted.internet import reactor

from config import DOMAINS_TO_BE_SKIPPED, START_URL, \
    MAX_CONCURRENT_REQUESTS_PER_SERVER, PHANTOM_JS_LOCATION, IDLE_PING_COUNT, \
    ERROR_CODES
from web_page import extract_domain, extract_base_site, WebPage


logging.basicConfig(filemode='w', level=logging.INFO)
handler = logging.FileHandler('scrapper.log')
logger = logging.getLogger(__name__)
logger.addHandler(handler)


def print_pages_to_file(file_name, identify_external, page_set,
                        filter_function=None):
    if not filter_function:
        filter_function = lambda wp: wp.external_url == identify_external \
                                     and wp.response_code not in ERROR_CODES \
                                     and 'text/html' in wp.content_type
    list_to_print = sorted(filter(filter_function, page_set))
    with open(file_name, 'w') as output_file:
        for page in list_to_print:
            output_file.write("{}\n".format(page.url))


def print_pages_with_errors(is_external_page, page_set):
    for error_code in ERROR_CODES:
        pages = sorted(
            filter((lambda wp: wp.external_url == is_external_page
                               and wp.response_code == error_code), page_set))
        pages.sort(key=lambda x: x.parent)
        parent_page = ''
        for page in pages:
            if parent_page != page.parent.url:
                parent_page = page.parent.url
                print(
                    "\nExamined {} : \nPages with response Code {} : ".format(
                        parent_page.encode('utf8'), error_code))
            print("{} ".format(page.url.encode('utf8')))


class SiteSpider:
    def __init__(self, start_url):
        self.visited_urls = set()
        self.intermediate_urls = set()
        self.logger = logging.getLogger(__name__)
        self.base_domain = extract_domain(start_url)
        self.base_site = extract_base_site(start_url)
        self.non_visited_urls = {
            WebPage(start_url, None, start_url, self.base_domain,
                    DOMAINS_TO_BE_SKIPPED)}
        self.added_count = 1
        self.idle_ping = 0
        self.coop = task.Cooperator()
        self.start_idle_counter = False

    def filter_visited_links(self, page):
        return page not in self.visited_urls \
               and page not in self.non_visited_urls \
               and page not in self.intermediate_urls

    def get_unique_non_visited_links(self, page):
        l = Lock()
        l.acquire()
        filtered_links = set(filter(self.filter_visited_links, page.links))
        l.release()
        return filtered_links

    def process_web_page(self, resp, web_page):
        logger.debug(
            "Called {} for {}".format('process_web_page',
                                      unicode(web_page.url).encode("utf-8")))
        self.visited_urls.add(web_page)
        self.intermediate_urls.discard(web_page)
        unique_links = self.get_unique_non_visited_links(web_page)
        self.non_visited_urls = self.non_visited_urls.union(unique_links)
        self.added_count += len(unique_links)
        self.start_idle_counter = True

    def generate_urls_to_visit(self):

        while self.idle_ping < IDLE_PING_COUNT:
            print "Total urls added :  {} , Total urls visited : {} , " \
                  "Total urls in process : {}  \r" \
                .format(self.added_count, len(self.visited_urls),
                        len(self.intermediate_urls))

            if len(self.non_visited_urls) > 0:
                self.idle_ping = 0
                web_page = self.non_visited_urls.pop()
                self.intermediate_urls.add(web_page)
                d = web_page.process()
                d.addCallback(self.process_web_page, web_page)
                yield d
            elif self.start_idle_counter:
                d = Deferred()
                reactor.callLater(0.1, d.callback, None)
                yield d
                self.idle_ping += 1
                if self.idle_ping == 300:
                    break
            else:
                d = Deferred()
                reactor.callLater(0.1, d.callback, None)
                yield d
        raise StopIteration

    def crawl(self):
        logger.debug("Called {}".format('crawl'))
        deferred_list = []
        coop = task.Cooperator()
        work = self.generate_urls_to_visit()
        for i in xrange(MAX_CONCURRENT_REQUESTS_PER_SERVER):
            d = coop.coiterate(work)
            deferred_list.append(d)
        dl = DeferredList(deferred_list)
        dl.addCallback(self.wrap_up)

    def wrap_up(self, resp):
        self.print_stats()
        reactor.stop()

    def print_stats(self):
        """
        Function to print the stats viz: pages with js errors , pages with 404
        error , external and internal pages .
        """
        print_pages_with_errors(True, self.visited_urls)
        print_pages_with_errors(False, self.visited_urls)

        print("\nTotal pages visited : {}\n".format(len(self.visited_urls)))

        print_pages_to_file("all_internal_pages.txt", False, self.visited_urls)
        print_pages_to_file("all_external_pages.txt", True, self.visited_urls)


def process_parameters():
    parser = argparse.ArgumentParser(description='A Simple website scrapper')
    parser.add_argument("--url",
                        help="the start url , defaults to the confog.ini url",
                        default=START_URL)
    parser.add_argument('--jserrors', dest='testjs', action='store_true')
    parser.add_argument('--no-jserrors', dest='testjs', action='store_false')
    parser.set_defaults(testjs=False)
    return parser.parse_args()


def invoke_url_in_browser(index):
    print("\n\nIdentifying the javascript and page loading errors\n\n")
    SCRIPT = 'trial.js'
    params = [PHANTOM_JS_LOCATION, SCRIPT, "all_internal_pages.txt", index]

    p = subprocess.Popen(params, stdout=subprocess.PIPE, bufsize=1)
    for line in iter(p.stdout.readline, b''):
        print line,
    p.communicate()


def worker(url):
    script = 'single_url_invoker.js'
    params = [PHANTOM_JS_LOCATION, script, url.strip('\n')]
    p = subprocess.Popen(params, stdout=subprocess.PIPE, bufsize=1)
    for line in iter(p.stdout.readline, b''):
        print line,
    p.communicate()


if __name__ == "__main__":

    args = process_parameters()
    base_url = args.url
    enable_js_tests = args.testjs

    scrapper = SiteSpider(base_url)
    reactor.callLater(2, scrapper.crawl)
    reactor.run()

    if enable_js_tests:
        print("\n\nIdentifying the javascript and page loading errors\n\n")
        SCRIPT = 'page_invoker.js'
        params = [PHANTOM_JS_LOCATION, SCRIPT, "all_internal_pages.txt", ""]
        p = subprocess.Popen(params, stdout=subprocess.PIPE, bufsize=1)
        for line in iter(p.stdout.readline, b''):
            print line,
        p.communicate()

        # fname= "all_internal_pages.txt"
        # content= []
        # with open(fname) as f:
        # content = f.readlines()
        #
        # threads = []
        # count = 0
        # pool = Pool(processes=50)
        # pool.map(worker, sorted(content))

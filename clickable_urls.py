import sublime
import sublime_plugin
import webbrowser
import threading

import os

class UrlHighlighter(sublime_plugin.EventListener):
    # Thanks Jeff Atwood http://www.codinghorror.com/blog/2008/10/the-problem-with-urls.html
    # ^ that up here is a URL that should be matched
    URL_REGEX = "\\bhttps?://[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
    FILE_URL_REGEX = "\\bfile?:///[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
    NOTE_URL_REGEX = "\\bnote?:///[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
    DEFAULT_MAX_URLS = 200
    SETTINGS_FILENAME = 'ClickableUrls.sublime-settings'

    urls_for_view = {}
    scopes_for_view = {}
    ignored_views = []
    browser = None
    highlight_semaphore = threading.Semaphore()

    def on_activated(self, view):
        self.update_url_highlights(view)

    # Blocking handlers for ST2
    def on_load(self, view):
        if sublime.version() < '3000':
            self.update_url_highlights(view)

    def on_modified(self, view):
        if sublime.version() < '3000':
            self.update_url_highlights(view)

    # Async listeners for ST3
    def on_load_async(self, view):
        self.update_url_highlights_async(view)

    def on_modified_async(self, view):
        self.update_url_highlights_async(view)

    def on_close(self, view):
        for map in [self.urls_for_view, self.scopes_for_view, self.ignored_views]:
            if view.id() in map:
                del map[view.id()]

    """The logic entry point. Find all URLs in view, store and highlight them"""
    def update_url_highlights(self, view):
    #     update_http_url_highlights(self, view)

    # def update_file_url_hightlights(self, view):


    # def update_http_url_highlights(self, view):
        settings = sublime.load_settings(UrlHighlighter.SETTINGS_FILENAME)
        should_highlight_urls = settings.get('highlight_urls', True)
        max_url_limit = settings.get('max_url_limit', UrlHighlighter.DEFAULT_MAX_URLS)

        if view.id() in UrlHighlighter.ignored_views:
            return

        urls = view.find_all(UrlHighlighter.URL_REGEX)
        file_urls = view.find_all(UrlHighlighter.FILE_URL_REGEX)
        note_urls = view.find_all(UrlHighlighter.NOTE_URL_REGEX)
        restruc_urls = view.find_all("`")

        print("RestructuredTextURL: " + str(restruc_urls))

        if len(restruc_urls) > 1:
            for i in range(0, len(restruc_urls)-1):
                possible_url_region = sublime.Region(restruc_urls[i].a,restruc_urls[i+1].b)
                possible_url = view.substr(possible_url_region)

                if possible_url[0] == '`' and ":" in possible_url:
                    i = possible_url.index(":")
                    possible_url = possible_url[0:i] + "`"
                    print("new url: " + possible_url)

                possible_url = possible_url[1:len(possible_url)-1]
                if not '\n' in possible_url:
                    possible_url_regex = "\\b_" + possible_url  + ": file?:///[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
                    new_url = view.find_all(possible_url_regex)
                    print("Possible URL? " + possible_url + " in region " + str(new_url))
                    if len(new_url) == 1:
                        urls.append(possible_url_region)
                    else:
                        possible_url_regex = "\\b_" + possible_url  + ": https?://[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
                        new_url = view.find_all(possible_url_regex)
                        print("Possible URL? " + possible_url + " in region " + str(new_url))
                        if len(new_url) == 1:
                            urls.append(possible_url_region)
                        else:
                            possible_url_regex = "\\b_" + possible_url  + ": note?:///[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
                            new_url = view.find_all(possible_url_regex)
                            print("Possible URL? " + possible_url + " in region " + str(new_url))
                            if len(new_url) == 1:
                                urls.append(possible_url_region)

        for u in file_urls:
            urls.append(u)

        for n in note_urls:
            urls.append(n)

        # Avoid slowdowns for views with too much URLs
        if len(urls) > max_url_limit:
            print("UrlHighlighter: ignoring view with %u URLs" % len(urls))
            UrlHighlighter.ignored_views.append(view.id())
            return

        UrlHighlighter.urls_for_view[view.id()] = urls

        should_highlight_urls = sublime.load_settings(UrlHighlighter.SETTINGS_FILENAME).get('highlight_urls', True)
        if (should_highlight_urls):
            self.highlight_urls(view, urls)

    """Same as update_url_highlights, but avoids race conditions with a
    semaphore."""
    def update_url_highlights_async(self, view):
        UrlHighlighter.highlight_semaphore.acquire()
        try:
            self.update_url_highlights(view)
        finally:
            UrlHighlighter.highlight_semaphore.release()

    """Creates a set of regions from the intersection of urls and scopes,
    underlines all of them."""
    def highlight_urls(self, view, urls):
        # We need separate regions for each lexical scope for ST to use a proper color for the underline
        scope_map = {}
        for url in urls:
            scope_name = view.scope_name(url.a)
            scope_map.setdefault(scope_name, []).append(url)

        for scope_name in scope_map:
            self.underline_regions(view, scope_name, scope_map[scope_name])

        self.update_view_scopes(view, scope_map.keys())

    """Apply underlining with provided scope name to provided regions.
    Uses the empty region underline hack for Sublime Text 2 and native
    underlining for Sublime Text 3."""
    def underline_regions(self, view, scope_name, regions):
        if sublime.version() >= '3019':
            # in Sublime Text 3, the regions are just underlined
            view.add_regions(
                u'clickable-urls ' + scope_name,
                regions,
                scope_name,
                flags=sublime.DRAW_NO_FILL|sublime.DRAW_NO_OUTLINE|sublime.DRAW_SOLID_UNDERLINE)
        else:
            # in Sublime Text 2, the 'empty region underline' hack is used
            char_regions = [sublime.Region(pos, pos) for region in regions for pos in range(region.a, region.b)]
            view.add_regions(
                u'clickable-urls ' + scope_name,
                char_regions,
                scope_name,
                sublime.DRAW_EMPTY_AS_OVERWRITE)

    """Store new set of underlined scopes for view. Erase underlining from
    scopes that were used but are not anymore."""
    def update_view_scopes(self, view, new_scopes):
        old_scopes = UrlHighlighter.scopes_for_view.get(view.id(), None)
        if old_scopes:
            unused_scopes = set(old_scopes) - set(new_scopes)
            for unused_scope_name in unused_scopes:
                view.erase_regions(u'clickable-urls ' + unused_scope_name)

        UrlHighlighter.scopes_for_view[view.id()] = new_scopes



def open_url(url):
    print('open_url ' + url)
    browser =  sublime.load_settings(UrlHighlighter.SETTINGS_FILENAME).get('clickable_urls_browser')
    try:
        webbrowser.get(browser).open(url, autoraise=True)
    except(webbrowser.Error):
        sublime.error_message('Failed to open browser. See "Customizing the browser" in the README.')

class OpenUrlUnderCursorCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if self.view.id() in UrlHighlighter.urls_for_view:
            selection = self.view.sel()[0]
            if selection.empty():
                selection = next((url for url in UrlHighlighter.urls_for_view[self.view.id()] if url.contains(selection)), None)
                if not selection:
                    return
            url = self.view.substr(selection)

            self.verify_url(url)

    def verify_markdown_url(self, url):
        print('verify_markdown_url')
        # Verify if url specifies a line
        line = None
        if url[0] == '`' and ":" in url:
            i = url.index(":")
            line = url[i+1:-1]
            url = url[0:i] + "`"
            print("new url: " + url + " and line " + str(line))

        if url[0] == '`' and url[len(url)-1] == '`':
            possible_url = url[1:len(url)-1]
            possible_url_regex = "\\b_" + possible_url  + ": file?:///[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
            new_url = self.view.find_all(possible_url_regex)
            print("Lets open URL? " + possible_url + " in region " + str(new_url))
            if len(new_url) == 1:
                url = self.view.substr(new_url[0])
                url = url[len(possible_url) + 3:]
                print("Trying to open " + url[8:])
                url_line = ""
                if line is not None:
                    url_line = ":" + line
                    if url_line.count(":") == 1:
                        url_line = url_line + ":0"
                if url.endswith(".pdf"):
                    open_url(url + (":" + str(line) if line is not None else ""))
                else:
                    self.view.window().open_file(url[7:] + url_line, sublime.ENCODED_POSITION)
                return True
            else:
                possible_url_regex = "\\b_" + possible_url  + ": https?://[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
                new_url = self.view.find_all(possible_url_regex)
                print("Possible URL? " + possible_url + " in region " + str(new_url))
                if len(new_url) == 1:
                    url = self.view.substr(new_url[0])
                    url = url[len(possible_url) + 3:]
                    print("Trying to open " + url)
                    open_url(url)
                    return True
                else:
                    possible_url_regex = "\\b_" + possible_url  + ": note?:///[-A-Za-z0-9+&@#/%?=~_()|!:,.;']*[-A-Za-z0-9+&@#/%=~_(|]"
                    new_url = self.view.find_all(possible_url_regex)
                    print("Possible URL? " + possible_url + " in region " + str(new_url))
                    if len(new_url) == 1:
                        url = self.view.substr(new_url[0])
                        url = url[len(possible_url) + 3:]
                        print("Trying to open " + url)
                        self.verify_note_url(url)
                        return True
        return False

    def verify_note_url(self, url):
        # Verify if url specifies a line
        line = None
        if url[0] =='`' and ":" in url:
            i = url.index(":")
            line = url[i+1:-1]
            url = url[0:i] + "`"

        if 'note://' in url:
            url = url.replace('%20', ' ')
            note_path = os.environ['HOME'] + '/Notes/' + url[7:] + '.note'
            print('verify_note_url: ' + note_path)

            self.view.window().open_file(note_path + (":" + str(line) if line is not None else ""))
            return False
        return False


    def verify_url(self, url):
        self.verify_markdown_url(url) or \
        self.verify_note_url(url) or \
        open_url(url)


class OpenAllUrlsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if self.view.id() in UrlHighlighter.urls_for_view:
            for url in set([self.view.substr(url_region) for url_region in UrlHighlighter.urls_for_view[self.view.id()]]):
                open_url(url)

class RemoveUnusedMarkdownUrls(sublime_plugin.TextCommand):
    def run(self, edit):
        current_file = self.view.file_name()

        print(current_file)

        if current_file is None:
            return

        file_lines = []
        with open(current_file, 'r', errors='replace') as text_file:
            file_lines = text_file.readlines()

        for line in file_lines:

            if line[0] == '_':
                point_index = line.index(':')
                if point_index != -1:
                    url_alias = line[1:point_index]
                    results = self.view.find_all("`" + url_alias + "`")
                    if results:
                        print(url_alias)
                    else:
                        region = self.view.find_all(line)
                        self.view.replace(edit, region[0], "")
                    # print(str(results))



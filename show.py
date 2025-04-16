import os
import re
from pathlib import Path

from flask import Flask, request, render_template, send_from_directory, abort
import traceback
import glob

app_folder = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(app_folder, 'templates'))

VER = "20250227"


def match_files(folder, index_pattern):
    # Remove parenthesis used for capture groups
    index_pattern_glob = index_pattern.replace('(', '').replace(')', '')
    index_pattern_regex = index_pattern.replace('*', '.+')
    matched_files = Path(folder).glob(index_pattern_glob)
    matcher = re.compile(index_pattern_regex)
    matched_files_data = []
    for matched_file in matched_files:
        match = matcher.match(matched_file.relative_to(folder).as_posix())
        if match:
            matched_files_data.append((matched_file.as_posix(), match.groups()))
    return matched_files_data

def format_column(value, groups):
    """Replace {$X} placeholders with matched regex groups"""
    for i, group in enumerate(groups):
        value = value.replace(f'${i+1}', group)
    return value

@app.route('/')
def index():
    config_file = request.args.get("config", "None")
    folder = request.args.get("folder", "None")
    page = request.args.get("page", 1)

    if page == "":
        page = 1
    page = int(page)

    config_file = os.path.expanduser(config_file)
    folder = os.path.expanduser(folder)

    error_msg = ""

    query_index = request.args.get("query_index", None)
    if query_index == '':
        query_index = None

    try:
        with open(config_file) as f:
            code = compile(f.read(), '', 'eval')
            config = eval(code)
    except Exception as e:
        config = {}
        error_msg = f"Error: Config file {config_file} cannot be read"
        traceback.print_exc()
   
    # print(config)

    kwargs = dict(
        config_file=config_file,
        folder=folder, 
        last_query_index=query_index
    )

    if len(config) > 0:
        matched_files_data = match_files(folder, config['index_pattern'])
        matched_files_data = sorted(matched_files_data, key=lambda x: x[0])

        if config.get("shuffle", False):
            import hashlib
            matched_files_data = sorted(matched_files_data, key=lambda x: int(hashlib.md5(x[0].encode()).hexdigest(), 16))
        
        if query_index is not None:
            # TODO SNB: handle this
            while query_index.startswith(' '):
                query_index = query_index[1:]
            prev_len = len(query_index) + 1
            while prev_len != len(query_index):
                prev_len = len(query_index)
                query_index = query_index.replace(', ', ',')

            query_index_list = list(query_index.split(","))
            filtered_files_data = []
            for matched_file_data in matched_files_data:
                matched_file_index = '/'.join(matched_file_data[1])
                for query_index in query_index_list:
                    if query_index in matched_file_index:
                        filtered_files_data.append(matched_file_data)
                        break
            matched_files_data = filtered_files_data

        columns = config.get("columns", [])
        column_heads = ["#"] + [c[0] for c in columns]

        rows = []
        images_per_page = config.get("images_per_page", 20)
        L = images_per_page * (int(page) - 1)
        R = images_per_page * int(page)

        skip_incomplete = config.get("skip_incomplete", False)

        for matched_file_data in matched_files_data[L:R]:
            row = [(None, '/'.join(matched_file_data[1]))]
            for column in columns:
                _, column_pattern = column
                if not column_pattern.startswith("/"):
                    column_pattern = os.path.join(folder, column_pattern)
                column_pattern = format_column(column_pattern, matched_file_data[1])

                column_image_candidates = glob.glob(os.path.join(folder, column_pattern))
                # print(column_pattern(index), column_image_candidates)
                if len(column_image_candidates) == 0:
                    column_image = column_pattern
                    if skip_incomplete:
                        row = None
                        break
                else:
                    column_image = column_image_candidates[0]

                contents = column_image
                if Path(column_image).suffix in ['.txt', '.json']:
                    try:
                        with open(column_image) as f:
                            contents = "\n".join(f.readlines())
                    except:
                        contents = f"Error: File {column_image} cannot be read"
                else:
                    from urllib.parse import quote
                    contents = quote(contents, encoding='utf-8')

                row.append((contents, column_image))

            if row is not None:
                rows.append(row)

        num_pages = (len(matched_files_data) + images_per_page - 1) // images_per_page
        page = max(page, 1)
        page = min(page, num_pages)
        navi = []
        prev_page = int(page) - 1
        next_page = int(page) + 1

        def url_at_page(p):
            return f"?config={config_file}&folder={folder}&page={p}"
        
        prev_page = None if prev_page < 1 else url_at_page(prev_page)
        next_page = None if next_page > num_pages else url_at_page(next_page)

        page_rad = 5

        if page - page_rad > 1:
            navi.append((
                1,
                url_at_page(1)
            ))

        if page - page_rad > 2:
            navi.append((
                "...",
                "..."
            ))

        for page_index in range(page - page_rad, page + page_rad + 1):
            if 1 <= page_index <= num_pages:
                navi.append((
                    page_index,
                    url_at_page(page_index) 
                ))

        if page + page_rad < num_pages - 1:
            navi.append((
                "...",
                "..."
            ))

        if page + page_rad < num_pages:
            navi.append((
                num_pages,
                url_at_page(num_pages)
            ))

        kwargs = dict(
            config_file=config_file,
            folder=folder,   
            column_heads=column_heads,
            rows=rows,
            page=page,
            prev_page=prev_page,
            next_page=next_page,
            navi=navi,
            error=error_msg != "",
            last_query_index=query_index,
            img_max_width=config.get("img_max_width", 1024),
            img_max_height=config.get("img_max_height", 256),
        )

    
    return render_template('fig_tab.html',
        title=config.get('title', error_msg),   
        ver=VER,
        **kwargs
    )


@app.route('/file')
def get_image():
    path = request.args.get("path", "None")
    path = os.path.abspath(path)
    try:
        return send_from_directory(os.path.dirname(path), os.path.basename(path))
    except FileNotFoundError:
        abort(404)

if __name__ == '__main__':
    import logging
    app.logger.setLevel(logging.ERROR)
    app.run(debug=False, port=8233, host="0.0.0.0") 
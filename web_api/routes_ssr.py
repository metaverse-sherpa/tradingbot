from flask import Blueprint, make_response
from web_api.ssr_renderer import generate_ssr_html

ssr_bp = Blueprint('ssr', __name__)

@ssr_bp.route('/ssr/', defaults={'path': ''})
@ssr_bp.route('/ssr/<path:path>')
def serve_ssr(path):
    html_content = generate_ssr_html("/" + path)
    response = make_response(html_content)
    response.headers['Content-Type'] = 'text/html'
    return response

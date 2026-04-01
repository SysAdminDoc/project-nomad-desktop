"""Flask blueprints for NOMAD Field Desk route modules."""

from flask import jsonify


def error_response(message, status_code=400, details=None):
    """Standardized JSON error response."""
    body = {'error': message, 'status': status_code}
    if details:
        body['details'] = details
    return jsonify(body), status_code

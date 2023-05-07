import json

class MultiplyNumbersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.get('Content-Type') == 'application/json' and request.GET.get('mock') == 'true':
            try:
                json_data = json.loads(response.content)
                self._multiply_numbers(json_data)
                response.content = json.dumps(json_data)
            except ValueError:
                pass

        return response

    def _multiply_numbers(self, data):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    data[key] = value * 0.13
                elif isinstance(value, dict):
                    self._multiply_numbers(value)
                elif isinstance(value, list):
                    self._multiply_numbers(value)
        elif isinstance(data, list):
            for item in data:
                self._multiply_numbers(item)

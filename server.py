import io, cgi, http.server, traceback
from image_processor import process_avasplit
from html_generator import generate_html_response, generate_no_gifs_html
from utils import clean_up_files

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = '''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Group Goes GIF</title>
        </head>
        <body>
            <div class="container">
                <h1>Group Goes GIF</h1>
                <form id="upload-form" enctype="multipart/form-data" method="post">
                    <input type="file" id="file-input" name="imageFile" accept="image/*" required>
                    <div id="file-name">No file chosen</div>
                    <button type="submit" id="submit-btn">Convert to GIF</button>
                </form>
            </div>
        </body>
        </html>
        '''
        self.wfile.write(html.encode())

    def do_POST(self):
        print("Entering do_POST method")
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        print(f"Received POST data of length: {content_length}")

        try:
            # Parse the multipart form data
            boundary = self.headers['Content-Type'].split("=")[1].encode()
            fields = cgi.parse_multipart(io.BytesIO(post_data), {"boundary": boundary})
            
            image_data = fields.get('imageFile', [b''])[0]
            if not image_data:
                raise ValueError("No image data received")

            gif_files = process_avasplit(image_data)
            
            if not gif_files:
                print("No GIF files generated. Sending disclaimer response.")
                html_response = generate_no_gifs_html()
            else:
                html_response = generate_html_response(gif_files)

            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html_response.encode())

        except Exception as e:
            print(f"Error in do_POST: {str(e)}")
            traceback.print_exc()
            error_html = generate_error_html(f"An error occurred: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(error_html.encode())

        print("Exiting do_POST method")

def generate_error_html(error_message):
    return f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Error - GROUP GOES GIF</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background-color: #f0f0f0;
            }}
            .error-container {{
                background-color: white;
                padding: 2rem;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                text-align: center;
            }}
            h1 {{
                color: #d32f2f;
            }}
            .back-link {{
                display: inline-block;
                margin-top: 1rem;
                color: #4CAF50;
                text-decoration: none;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="error-container">
            <h1>Error</h1>
            <p>{error_message}</p>
            <a href="/" class="back-link">Back to Upload</a>
        </div>
    </body>
    </html>
    '''
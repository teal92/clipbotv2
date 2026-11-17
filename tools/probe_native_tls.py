"""Exercise an actual native FFmpeg TLS client against disposable loopback hosts.

No production connections, system trust changes or reusable private keys.
"""
import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import wave


def check_results(results):
    if (set(results) != {'trusted','untrusted','wrongHostname'}
            or any(type(value) is not int for value in results.values())
            or results['trusted'] != 0 or results['untrusted'] == 0 or results['wrongHostname'] == 0):
        raise ValueError('Native FFmpeg TLS acceptance/rejection checks failed.')
    return {name:True for name in results}


def certificate_rejection(code,stderr):
    message=stderr.decode('utf-8','replace').lower()
    return code!=0 and any(marker in message for marker in (
        'certificate verify failed','certificate verification failed','hostname mismatch'))


def ffmpeg_arguments(ffmpeg, roots, port):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Use a loopback TLS probe port.')
    return [str(ffmpeg),'-nostdin','-hide_banner','-loglevel','error',
            '-rw_timeout','3000000','-tls_verify','1','-ca_file',str(roots),
            '-i',f'https://localhost:{port}/probe.wav','-t','0.1','-f','null','-']


@contextmanager
def endpoint(certificate, key):
    buffer = io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00'*16000)
    payload = buffer.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def do_GET(self):
            if self.path != '/probe.wav':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type','audio/wav')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError,ssl.SSLError):
                pass

    server = HTTPServer(('127.0.0.1',0),Handler)
    server.timeout = 5
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate,key)
    server.socket = context.wrap_socket(server.socket,server_side=True)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def probe(ffmpeg, openssl='/usr/bin/openssl'):
    ffmpeg, openssl = Path(ffmpeg).resolve(), Path(openssl).resolve()
    if not ffmpeg.is_file() or not openssl.is_file():
        raise ValueError('Explicit native FFmpeg and certificate-tool paths are required.')
    environment = {key:value for key,value in os.environ.items()
                   if not key.startswith(('CLIPBOT_','ANTHROPIC_','STRIPE_','RESEND_'))}
    with tempfile.TemporaryDirectory(prefix='clipbot-tls-probe-') as folder:
        root = Path(folder).resolve()
        root.chmod(0o700)
        for name,hostname in (('trusted','localhost'),('untrusted','localhost'),('wrongHostname','wrong.example.invalid')):
            config = root/(name+'.cnf')
            config.write_text('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ext\n'
                '[dn]\nCN='+hostname+'\n[ext]\nsubjectAltName=DNS:'+hostname+'\n'
                'basicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
            subprocess.run([str(openssl),'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                '-config',str(config),
                '-keyout',str(root/(name+'.key')),'-out',str(root/(name+'.pem'))],
                env=environment,check=True,capture_output=True,timeout=30)
            (root/(name+'.key')).chmod(0o600)
        results = {}
        for name in ('trusted','untrusted','wrongHostname'):
            # Wrong-host certificate is explicitly trusted: a rejection must
            # therefore exercise hostname verification, not just missing trust.
            trust = root/('wrongHostname.pem' if name=='wrongHostname' else 'trusted.pem')
            with endpoint(root/(name+'.pem'),root/(name+'.key')) as port:
                result = subprocess.run(ffmpeg_arguments(ffmpeg,trust,port),env=environment,
                    capture_output=True,timeout=15)
                if name!='trusted' and not certificate_rejection(result.returncode,result.stderr):
                    raise ValueError('Native TLS negative case did not prove certificate rejection: '+name)
                results[name] = result.returncode
        return {'checks':check_results(results),'systemTrustChanged':False,'publicReleaseApproved':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    arguments = parser.parse_args()
    receipt = probe(arguments.ffmpeg)
    with arguments.report.open('x') as output:
        json.dump(receipt,output,indent=2)

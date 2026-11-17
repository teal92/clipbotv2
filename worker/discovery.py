"""Metadata discovery via paired service; provider tokens remain on the server."""
def discover(client):return client.request('GET','/api/worker/discovery')

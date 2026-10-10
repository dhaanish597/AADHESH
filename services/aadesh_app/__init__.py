"""`aadesh_app` -- the shared application layer behind every HTTP skin.

It holds ports and no clients: no boto3, no sockets, no filesystem access to anything it was
not handed. The local `http.server` skin and the AWS Lambda skin both construct an
`AadeshApplication` with their own adapters, which is what makes "the same logic runs locally
and on AWS" a fact that can be checked rather than a claim in a slide.
"""

from __future__ import annotations

from aadesh_app.application import AadeshApplication

__all__ = ["AadeshApplication"]

"""roadrecon-gui: serve the GUI and API on a roadrecon database."""
import argparse
import json


def main(args=None):
    parser = argparse.ArgumentParser(add_help=True, description='ROADrecon GUI')
    parser.add_argument('-d', '--database', action='store', default='roadrecon.db',
                        help='Database file or SQLAlchemy URL. Default: roadrecon.db in the current directory')
    parser.add_argument('--host', default='127.0.0.1', help='Host to listen on (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000, help='Port to listen on (default: 5000)')
    parser.add_argument('--read-only', action='store_true',
                        help='Never write to the database (no index creation); for evidence copies')
    parser.add_argument('--openapi', metavar='FILE', help='Write the OpenAPI schema to FILE and exit')
    args = parser.parse_args(args)

    from .app import create_app
    app = create_app(args.database, args.read_only)
    if args.openapi:
        with open(args.openapi, 'w') as f:
            json.dump(app.openapi(), f, indent=1)
            f.write('\n')
        return
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()

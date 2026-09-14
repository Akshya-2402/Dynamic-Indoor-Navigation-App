from app import app
if __name__ == '__main__':
    # Run on 127.0.0.1:5001 to avoid conflicts
    app.run(debug=True, use_reloader=False, host='127.0.0.1', port=5001)

from flask import Flask, render_template, request, jsonify
import requests
import os
import base64
import json
import stripe
import smtplib
import time
import random
import re
from email.mime.text import MIMEText

app = Flask(__name__)

# --- CONFIGURACIÓN DE STRIPE ---
stripe.api_key = "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"

# --- CONFIGURACIÓN DE PAYPAL ---
PAYPAL_CLIENT_ID = "TU_CLIENT_ID_DE_PAYPAL"
PAYPAL_CLIENT_SECRET = "TU_CLIENT_SECRET_DE_PAYPAL"
PAYPAL_API_BASE = "https://api-m.paypal.com" # Producción

def get_paypal_access_token():
    auth = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}
    data = "grant_type=client_credentials"
    response = requests.post(f"{PAYPAL_API_BASE}/v1/oauth2/token", headers=headers, data=data)
    return response.json().get("access_token") if response.status_code == 200 else None

@app.after_request
def add_header(response):
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    return response

@app.route('/')
def index():
    return render_template('index.html')

# --- ENDPOINT PARA CHECKER STRIPE (MANTENIDO) ---
@app.route('/process_stripe_payment', methods=['POST'])
def process_stripe_payment():
    data = request.json
    try:
        # Lógica original de creación de payment method
        pm = stripe.PaymentMethod.create(
            type="card",
            card={
                "number": data['card'],
                "exp_month": int(data['mm']),
                "exp_year": int(data['yyyy']),
                "cvc": data['cvv'],
            },
        )
        return jsonify({"status": "success", "message": "Payment Method Creado", "id": pm.id})
    except stripe.error.CardError as e:
        return jsonify({"status": "error", "message": e.user_message})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# --- ENDPOINT PARA CHECKER PAYPAL ---
@app.route('/api/paypal/create-order', methods=['POST'])
def create_paypal_order():
    data = request.json
    amount = data.get('amount', '2.50')
    token = get_paypal_access_token()
    if not token:
        return jsonify({'error': 'No se pudo autenticar con PayPal'}), 500

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{"amount": {"currency_code": "USD", "value": amount}}]
    }
    response = requests.post(f"{PAYPAL_API_BASE}/v2/checkout/orders", headers=headers, json=payload)
    if response.status_code == 201:
        return jsonify(response.json())
    return jsonify({'error': 'Error al crear la orden'}), response.status_code

@app.route('/api/paypal/capture-order', methods=['POST'])
def capture_paypal_order():
    data = request.json
    order_id = data.get('orderID')
    token = get_paypal_access_token()
    if not token:
        return jsonify({'error': 'No se pudo autenticar'}), 500

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture", headers=headers)
    if response.status_code == 201:
        return jsonify(response.json())
    return jsonify({'error': 'Error al capturar el pago'}), response.status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
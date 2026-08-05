# importing requirements
import json
import os
from datetime import datetime

def load_orders():
    orders_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),                  "../orders.json")
    with open(orders_path, "r", encoding="utf-8") as f:
        orders = json.load(f)
    return orders
    
orders = load_orders()
output_list = []

def check_each_order(order : dict):
    order_id = order["order_id"]
    membership = order["membership"]
    items = order["items"]

    total_shipping_fee = 0
    total_shopping_fee = 0

    sellers = {}
    #how sellers are going to look likes and how we sort each order by sellers
    #sellers = {
    #     "xyz" : [ "item1" , "item2" , "item3" , "...."],
    #     "hmg" : [ "item1" , "item2" , "item3" , "...."]
    #}

    # SORTING each order items by SELLERS
    for item in items:
        if item["seller_id"] in sellers:
            sellers[item["seller_id"]].append(item)
        else:
            sellers[item["seller_id"]] = [item]

    shipments = []
    for seller_id , items in sellers.items():
        shipping_fee = calculate_items_shipping_fee(order , items)
        total_shipping_fee += shipping_fee
        total_shopping_fee += calculate_items_shopping_fee(items)
        shipments.append({
            "seller_id": seller_id,
            "shipping_fee": round(shipping_fee)
        })

    # Checking free shipping situations
    if membership == "plus" or total_shopping_fee >= 500000:
            total_shipping_fee = 0
            for shipment in shipments:
                shipment["shipping_fee"] = 0
            updating_output_list(order_id , shipments , round(total_shipping_fee))
            return
    
    if total_shipping_fee > 200000:
            total_shipping_fee = 200000

    updating_output_list(
            order_id,
            shipments,
            round(total_shipping_fee)
        )

def calculate_items_shipping_fee(order: dict, items: list) -> float:
    if check_bulky(items):
        return 150000

    total_weight = sum(item["weight_grams"] for item in items)
    items_fee = calculate_over_weight(total_weight)

    items_fee += check_city_tier(order["city_tier"])

    if not check_time(order["created_at"]):
        items_fee *= 1.1

    items_fee += check_payment_method(order["payment_method"])

    return items_fee

def calculate_items_shopping_fee(items : list) -> float:
    total = 0
    for item in items:
        total += (item['unit_price'] * item['quantity']) - item['discount']
    return total

def check_bulky(items : list) -> bool:
    for item in items:
            if item["is_bulky"]:
                return True
    return False

def calculate_over_weight(weight_grams):
    extra_weight = max(0, weight_grams - 1000)
    over_weight_cost = -(-extra_weight // 500) * 5000
    return over_weight_cost

def updating_output_list( order_id: str , shipments_list: list , total_shipping_fee : float):
    output_list.append(
        {
            "order_id" : order_id,
            "shipments" : shipments_list,
             "total_shipping_fee" : total_shipping_fee
        }
    )

def check_time(dt_str: str):
    dt = datetime.fromisoformat(dt_str)
    hour = dt.hour
    if hour >= 23 or hour < 6:
        return False
    return True

def check_city_tier( city_tier : str) -> float:
    if city_tier == "tehran":
        return 25000
    elif city_tier == "provincial_capital":
        return 35000
    else:
        return 50000

def check_payment_method( payment_method : str ) -> float:
    if payment_method == "online":
        return 0
    else:
        return 10000

def save_output(output_list: list):
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_list, f, ensure_ascii=False, indent=2)

for order in orders:
    check_each_order(order)

save_output(output_list)

print("the final complete output is :  " , output_list)

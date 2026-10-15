from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from supabase import create_client, Client
import os
import time
import requests

SUPABASE_URL = "https://bwtvxhuqdzggtcbaihee.supabase.co"
SUPABASE_KEY = "sb_publishable_gYrEyp5GDhhpVo7TX_Emfg_Kafpym4v"

# Beem SMS Credentials
BEEM_API_KEY = "5bb1add52bce5f58"
BEEM_SECRET_KEY = "NzJmYjJmMWQyMTc1ZDViODVhZTE2MTJlZDFmZjAzNzZhYzhkNjhmMTgwYmI3YzNkYmE2YmIzZDhkYTQ0ZGVjNw=="
SENDER_ID = "KITENGO BAR"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    supabase = None

app = FastAPI(title="Kitengo Bar - Enterprise Edition")

PENDING_BILLS_STORE: Dict[str, dict] = {}

def format_proper_case(text: str) -> str:
    if not text:
        return ""
    return " ".join(word.capitalize() for word in text.strip().split())

def send_beem_sms(dest_phone: str, message: str):
    if not dest_phone:
        return False
        
    phone_clean = dest_phone.strip().replace("+", "").replace(" ", "")
    if phone_clean.startswith("0"):
        phone_clean = "255" + phone_clean[1:]
        
    url = "https://api.beem.africa/v1/send-sms"
    payload = {
        "source_addr": SENDER_ID,
        "schedule_time": "",
        "encoding": "0",
        "message": message,
        "recipients": [{"recipient_id": 1, "dest_addr": phone_clean}]
    }

    try:
        response = requests.post(url, json=payload, auth=(BEEM_API_KEY, BEEM_SECRET_KEY), timeout=10)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"SMS Sending failed: {e}")
        return False

class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "Cashier"
    salary: Optional[float] = 0.0

class PasswordChange(BaseModel):
    username: str
    old_password: str
    new_password: str

class UserManageRequest(BaseModel):
    username: str
    action: str
    new_password: Optional[str] = None

class CustomerCreate(BaseModel):
    full_name: str
    phone_number: str
    address: Optional[str] = ""
    initial_debt: Optional[float] = 0.0  # Umeongezwa hapa kusoma deni la awali

class ProductCreate(BaseModel):
    product_name: str
    buying_price: float
    selling_price: float
    stock_quantity: int
    recorded_by: str = "Admin"

class ProductUpdateRequest(BaseModel):
    id: int
    product_name: str
    buying_price: float
    selling_price: float
    stock_quantity: int

class ProductDeleteRequest(BaseModel):
    id: int

class StockInRequest(BaseModel):
    product_name: str
    added_quantity: int
    new_buying_price: Optional[float] = None
    recorded_by: str = "Admin"

class DeleteStockHistoryRequest(BaseModel):
    id: Optional[int] = None
    product_name: Optional[str] = None
    recorded_by: Optional[str] = "ALL"

class CartItemModel(BaseModel):
    product_name: str
    quantity: int
    unit_price: Optional[float] = 0.0

class CartStockAdjustModel(BaseModel):
    product_name: str
    quantity_change: int

class CartCheckoutModel(BaseModel):
    items: List[CartItemModel]
    cashier: str
    customer_name: Optional[str] = "Walk-in Customer"
    customer_phone: Optional[str] = None
    paid_amount: float
    payment_type: str = "Cash"
    pending_bill_id: Optional[str] = None

class SavePendingBillModel(BaseModel):
    bill_id: Optional[str] = None
    cashier: str
    customer_name: Optional[str] = "Walk-in Customer"
    customer_phone: Optional[str] = None
    items: List[CartItemModel]

class DebtPaymentRequest(BaseModel):
    customer_name: str
    amount_paid: float
    cashier: str

class ManualSaleRequest(BaseModel):
    sale_date: str
    amount: float
    description: str
    recorded_by: str

class ExpenseRequest(BaseModel):
    expense_date: str
    category: str
    amount: float
    description: str
    recorded_by: str

class LoanCalculationRequest(BaseModel):
    principal: float
    annual_rate: float
    months: int

class LoanCreate(BaseModel):
    customer_name: str
    principal: float
    annual_rate: float
    months: int

@app.post("/api/auth/login")
def login(user: UserLogin):
    try:
        u_clean = user.username.strip().lower()
        p_clean = user.password.strip()
        if u_clean == "admin" and p_clean == "gilberto":
            return {"status": "success", "username": "Admin", "role": "Admin", "can_manage_stock": True}
        if not supabase:
            raise HTTPException(status_code=500, detail="Hakuna muunganisho wa Database!")
        
        res = supabase.table("users").select("*").ilike("username", user.username.strip()).execute()
        if not res.data:
            raise HTTPException(status_code=401, detail="Jina la mtumiaji halipo!")
        db_user = res.data[0]
        if db_user.get("status") == "Blocked":
            raise HTTPException(status_code=403, detail="Akaunti yako imefungwa na Admin!")
        stored_pass = db_user.get("password_hash") or db_user.get("password")
        if stored_pass != user.password.strip():
            raise HTTPException(status_code=401, detail="Neno la siri si sahihi!")
        return {
            "status": "success", 
            "username": db_user["username"], 
            "role": db_user.get("role", "Cashier"),
            "can_manage_stock": db_user.get("can_manage_stock", False)
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/users/add")
def add_user(user: UserCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        user_data = {"username": user.username.strip(), "password_hash": user.password.strip(), "role": user.role, "salary": user.salary, "status": "Active", "can_manage_stock": False}
        res = supabase.table("users").insert(user_data).execute()
        return {"status": "success", "message": "Mtumiaji amesajiliwa mafanikio!", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/users")
def get_users():
    if not supabase:
        return {"status": "success", "data": [{"username": "Admin", "password": "gilberto", "role": "Admin", "salary": 0, "status": "Active", "cashier_debt": 0, "can_manage_stock": True}]}
    try:
        res = supabase.table("users").select("*").order("username", desc=False).execute()
        users_list = []
        sales_res = supabase.table("bar_sales").select("*").execute()
        all_sales = sales_res.data if sales_res.data else []

        pay_res = supabase.table("debt_payments").select("*").eq("status", "Approved").execute()
        approved_payments = pay_res.data if pay_res.data else []

        for u in res.data:
            uname = u.get("username")
            initial_debt = sum(s.get("debt_amount", 0) for s in all_sales if s.get("cashier") == uname)
            repaid_debt = sum(p.get("amount_paid", 0) for p in approved_payments if p.get("cashier") == uname)
            cashier_net_debt = max(0.0, initial_debt - repaid_debt)
            
            users_list.append({
                "id": u.get("id"),
                "username": uname,
                "password": u.get("password_hash") or u.get("password"),
                "role": u.get("role", "Cashier"),
                "salary": u.get("salary", 0),
                "status": u.get("status", "Active"),
                "cashier_debt": cashier_net_debt,
                "can_manage_stock": u.get("can_manage_stock", False)
            })
        return {"status": "success", "data": users_list}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/users/manage")
def manage_user(req: UserManageRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        res = supabase.table("users").select("*").ilike("username", req.username.strip()).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Mtumiaji hajapatikana!")
        db_user = res.data[0]
        user_id = db_user.get("id")
        if req.action == "delete":
            supabase.table("users").delete().eq("id", user_id).execute()
            return {"status": "success", "message": f"Mtumiaji {req.username} amefutwa kabisa!"}
        elif req.action == "toggle_status":
            current_status = db_user.get("status", "Active")
            new_status = "Blocked" if current_status == "Active" else "Active"
            supabase.table("users").update({"status": new_status}).eq("id", user_id).execute()
            return {"status": "success", "message": f"Hali ya mtumiaji imebadilishwa kuwa {new_status}!"}
        elif req.action == "toggle_stock_access":
            current_access = db_user.get("can_manage_stock", False)
            new_access = not current_access
            supabase.table("users").update({"can_manage_stock": new_access}).eq("id", user_id).execute()
            status_text = "Ruhusa ya Stock Imewashwa" if new_access else "Ruhusa ya Stock Imeondolewa"
            return {"status": "success", "message": status_text}
        elif req.action == "change_password":
            if not req.new_password:
                raise HTTPException(status_code=400, detail="Weka neno jipya la siri!")
            supabase.table("users").update({"password_hash": req.new_password.strip()}).eq("id", user_id).execute()
            return {"status": "success", "message": f"Neno la siri la {req.username} limebadilishwa!"}
        else:
            raise HTTPException(status_code=400, detail="Kitendo hakijulikani!")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/users/change-password")
def change_password(data: PasswordChange):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        res = supabase.table("users").select("*").ilike("username", data.username.strip()).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Mtumiaji hajapatikana!")
        db_user = res.data[0]
        stored_pass = db_user.get("password_hash") or db_user.get("password")
        if stored_pass != data.old_password.strip():
            raise HTTPException(status_code=400, detail="Neno la siri la zamani si sahihi!")
        supabase.table("users").update({"password_hash": data.new_password.strip()}).eq("id", db_user["id"]).execute()
        return {"status": "success", "message": "Neno la siri limebadilishwa mafanikio!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/products")
def get_products(q: Optional[str] = None):
    if not supabase:
        return {"status": "success", "data": []}
    try:
        query = supabase.table("products").select("*")
        if q:
            query = query.ilike("product_name", f"%{q}%")
        res = query.order("product_name", desc=False).execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/products/add")
def add_product(product: ProductCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        clean_name = format_proper_case(product.product_name)
        existing = supabase.table("products").select("*").ilike("product_name", clean_name).execute()
        if existing.data:
            p_exist = existing.data[0]
            raise HTTPException(
                status_code=400, 
                detail=f"Bidhaa '{p_exist['product_name']}' TAYARI IPO KWENYE MFUMO (Stock iliyopo: {p_exist['stock_quantity']} pcs)! Tafadhali tumia sehemu ya 'Ongeza Stock' badala ya kusajili upya."
            )

        unit_buy = round(product.buying_price, 2)
        prod_data = {
            "product_name": clean_name,
            "buying_price": unit_buy,
            "selling_price": product.selling_price,
            "stock_quantity": product.stock_quantity
        }
        res = supabase.table("products").insert(prod_data).execute()
        
        supabase.table("stock_history").insert({
            "product_name": clean_name,
            "quantity_added": product.stock_quantity,
            "buying_price": unit_buy,
            "recorded_by": product.recorded_by
        }).execute()

        return {"status": "success", "message": f"Bidhaa '{clean_name}' imeongezwa!", "data": res.data}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/products/update")
def update_product_direct(p: ProductUpdateRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        clean_name = format_proper_case(p.product_name)
        update_data = {"product_name": clean_name, "buying_price": p.buying_price, "selling_price": p.selling_price, "stock_quantity": p.stock_quantity}
        supabase.table("products").update(update_data).eq("id", p.id).execute()
        return {"status": "success", "message": "Bidhaa imesasishwa mafanikio!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/products/delete")
def delete_product_permanently(req: ProductDeleteRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        prod_res = supabase.table("products").select("*").eq("id", req.id).execute()
        if not prod_res.data:
            raise HTTPException(status_code=404, detail="Bidhaa haijapatikana!")
        p = prod_res.data[0]
        prod_name = p.get("product_name")

        supabase.table("products").delete().eq("id", req.id).execute()
        return {"status": "success", "message": f"Bidhaa '{prod_name}' imefutwa kwenye mfumo!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/products/stock-in")
def stock_in(stock: StockInRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        clean_name = format_proper_case(stock.product_name)
        prod_res = supabase.table("products").select("*").ilike("product_name", clean_name).execute()
        if not prod_res.data:
            raise HTTPException(status_code=404, detail="Bidhaa haijapatikana kwenye stock!")
        product = prod_res.data[0]
        old_qty = product["stock_quantity"]
        new_qty = old_qty + stock.added_quantity
        
        unit_buy_price = round(stock.new_buying_price, 2) if stock.new_buying_price is not None else product["buying_price"]
        
        update_data = {"stock_quantity": new_qty, "buying_price": unit_buy_price}
        supabase.table("products").update(update_data).eq("id", product["id"]).execute()
        
        supabase.table("stock_history").insert({
            "product_name": product["product_name"],
            "quantity_added": stock.added_quantity,
            "buying_price": unit_buy_price,
            "recorded_by": stock.recorded_by
        }).execute()

        return {"status": "success", "message": f"Stock ya '{product['product_name']}' imesasishwa!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/stock/history")
def get_stock_history():
    if not supabase:
        return {"status": "success", "data": []}
    try:
        res = supabase.table("stock_history").select("*").order("created_at", desc=True).execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/stock/history/delete")
def delete_stock_history_entry(req: DeleteStockHistoryRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        if req.id:
            supabase.table("stock_history").delete().eq("id", req.id).execute()
            return {"status": "success", "message": "Rekodi ya historia imefutwa kikamilifu!"}
        elif req.product_name:
            p_name = format_proper_case(req.product_name)
            query = supabase.table("stock_history").delete().ilike("product_name", p_name)
            if req.recorded_by and req.recorded_by != "ALL":
                query = query.eq("recorded_by", req.recorded_by)
            query.execute()
            return {"status": "success", "message": f"Historia ya ununuzi wa '{p_name}' imefutwa kikamilifu!"}
        else:
            raise HTTPException(status_code=400, detail="Taarifa haitoshi kufuta rekodi!")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/pos/cart/adjust-stock")
def adjust_cart_stock(req: CartStockAdjustModel):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        clean_name = format_proper_case(req.product_name)
        prod_res = supabase.table("products").select("*").ilike("product_name", clean_name).execute()
        if not prod_res.data:
            raise HTTPException(status_code=404, detail=f"Bidhaa '{clean_name}' haijapatikana!")
        
        product = prod_res.data[0]
        current_stock = product["stock_quantity"]
        new_stock = current_stock - req.quantity_change
        if new_stock < 0:
            raise HTTPException(status_code=400, detail=f"Stock haitoshi! Zimebaki pcs {current_stock} tu.")
            
        supabase.table("products").update({"stock_quantity": new_stock}).eq("id", product["id"]).execute()
        return {"status": "success", "new_stock": new_stock}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/manual-sales/add")
def add_manual_sale(req: ManualSaleRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        data = {
            "txn_id": f"MS-{int(time.time())}",
            "txn_type": "Manual Sale",
            "transaction_type": "Manual Sale",
            "amount": req.amount,
            "description": f"{req.description} [Tarehe: {req.sale_date}]",
            "recorded_by": req.recorded_by
        }
        supabase.table("transactions").insert(data).execute()
        return {"status": "success", "message": "Mauzo ya manual yamewekwa kwenye kumbukumbu!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/expenses/add")
def add_expense(req: ExpenseRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        data = {
            "txn_id": f"EXP-{int(time.time())}",
            "txn_type": "Daily Expense",
            "transaction_type": f"Expense ({req.category})",
            "amount": req.amount,
            "description": f"{req.description} [Tarehe: {req.expense_date}]",
            "recorded_by": req.recorded_by
        }
        supabase.table("transactions").insert(data).execute()
        return {"status": "success", "message": "Matumizi yamerekodiwa kikamilifu!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/pos/pending/save")
def save_pending_bill(req: SavePendingBillModel):
    try:
        if not req.items:
            raise HTTPException(status_code=400, detail="Huwezi kuhifadhi bili isiyo na bidhaa!")
        
        bill_id = req.bill_id or f"PENDING-{int(time.time()*1000)}"
        cashier = req.cashier.strip()
        cust_name = format_proper_case(req.customer_name) if req.customer_name else "Walk-in Customer"
        cust_phone = req.customer_phone.strip() if req.customer_phone else None

        items_data = [{"product_name": i.product_name, "quantity": i.quantity, "unit_price": i.unit_price or 0} for i in req.items]

        PENDING_BILLS_STORE[bill_id] = {
            "bill_id": bill_id,
            "cashier": cashier,
            "customer_name": cust_name,
            "customer_phone": cust_phone,
            "items": items_data,
            "updated_at": time.time()
        }

        if cust_phone:
            total = sum(i["quantity"] * i["unit_price"] for i in items_data)
            items_summary = ", ".join([f"{i['product_name']} x{i['quantity']}" for i in items_data])
            msg = f"Habari {cust_name}, Bili yako ya KITENGO BAR imesasishwa:\nBidhaa: {items_summary}\nJumla Kuu: TZS {total:,.0f}.\nKaribu tena!"
            sms_sent = send_beem_sms(cust_phone, msg)
            msg_res = "Bili imehifadhiwa na SMS imetumwa kwa mteja!" if sms_sent else "Bili imehifadhiwa (SMS haikutumwa - tatizo la mtandao)!"
        else:
            msg_res = "Bili imehifadhiwa mafanikio!"

        return {"status": "success", "message": msg_res, "bill_id": bill_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/pos/pending/list")
def get_pending_bills(cashier: Optional[str] = None):
    try:
        bills = list(PENDING_BILLS_STORE.values())
        if cashier and cashier != "ALL":
            bills = [b for b in bills if b.get("cashier", "").lower() == cashier.lower()]
        bills.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return {"status": "success", "data": bills}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/pos/pending/delete/{bill_id}")
def delete_pending_bill(bill_id: str):
    try:
        if bill_id in PENDING_BILLS_STORE:
            del PENDING_BILLS_STORE[bill_id]
            return {"status": "success", "message": "Bili imefutwa!"}
        return {"status": "success", "message": "Bili haipatikani"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/pos/sell-cart")
def process_cart_sale(checkout: CartCheckoutModel):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        if not checkout.items:
            raise HTTPException(status_code=400, detail="Kikapu (Cart) hakina bidhaa yoyote!")
        
        cart_details = []
        total_cart_price = 0.0
        
        for item in checkout.items:
            clean_pname = format_proper_case(item.product_name)
            prod_res = supabase.table("products").select("*").ilike("product_name", clean_pname).execute()
            if not prod_res.data:
                raise HTTPException(status_code=404, detail=f"Bidhaa '{clean_pname}' haijapatikana kwenye stock!")
            product = prod_res.data[0]
            
            unit_price = product["selling_price"]
            item_total = item.quantity * unit_price
            total_cart_price += item_total
            
            cart_details.append({
                "product": product,
                "clean_name": clean_pname,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "total_price": item_total
            })
        
        paid_remaining = checkout.paid_amount
        change_amount = max(0.0, checkout.paid_amount - total_cart_price)
        total_debt = max(0.0, total_cart_price - checkout.paid_amount)

        sales_count_res = supabase.table("bar_sales").select("id", count="exact").execute()
        count = len(sales_count_res.data) if sales_count_res.data else 0
        bill_id = f"BILL-{count + 1001}"
        
        cust_name = format_proper_case(checkout.customer_name) if checkout.customer_name else "Walk-in Customer"
        
        for detail in cart_details:
            item_paid = min(paid_remaining, detail["total_price"])
            paid_remaining -= item_paid
            item_debt = detail["total_price"] - item_paid
            
            sale_data = {
                "bill_id": bill_id,
                "customer_name": cust_name,
                "cashier": checkout.cashier,
                "product_name": detail["clean_name"],
                "quantity": detail["quantity"],
                "unit_price": detail["unit_price"],
                "total_price": detail["total_price"],
                "paid_amount": item_paid,
                "debt_amount": item_debt,
                "payment_type": checkout.payment_type,
                "status": "Completed" if item_debt == 0 else "Partial"
            }
            supabase.table("bar_sales").insert(sale_data).execute()
        
        if total_debt > 0 and cust_name != "Walk-in Customer":
            cust_res = supabase.table("customers").select("*").ilike("full_name", cust_name).execute()
            if cust_res.data:
                c_id = cust_res.data[0]["id"]
                curr_debt = cust_res.data[0].get("total_debt", 0) or 0
                supabase.table("customers").update({"total_debt": curr_debt + total_debt}).eq("id", c_id).execute()
            else:
                supabase.table("customers").insert({"full_name": cust_name, "phone_number": checkout.customer_phone or "N/A", "address": "Deni la Mauzo", "total_debt": total_debt}).execute()
        
        if checkout.pending_bill_id and checkout.pending_bill_id in PENDING_BILLS_STORE:
            del PENDING_BILLS_STORE[checkout.pending_bill_id]

        return {
            "status": "success",
            "message": "Mauzo ya Cart yamekamilika!",
            "bill_id": bill_id,
            "total_amount": total_cart_price,
            "paid_amount": checkout.paid_amount,
            "change_amount": change_amount,
            "debt_amount": total_debt,
            "cashier": checkout.cashier,
            "customer_name": cust_name,
            "items": cart_details
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/pos/sales")
def get_bar_sales():
    if not supabase:
        return {"status": "success", "data": []}
    try:
        res = supabase.table("bar_sales").select("*").execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/customers/add")
def add_customer(customer: CustomerCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        clean_name = format_proper_case(customer.full_name)
        phone = customer.phone_number or "N/A"
        addr = customer.address or "N/A"
        initial_debt = customer.initial_debt or 0.0

        # Angalia kama mteja yupo tayari kwenye database
        existing = supabase.table("customers").select("*").ilike("full_name", clean_name).execute()
        
        if existing.data:
            # Kama yupo, jumuisha deni lake la awali na deni lililopo sasa
            cust_record = existing.data[0]
            c_id = cust_record["id"]
            current_total_debt = float(cust_record.get("total_debt", 0) or 0)
            new_total_debt = current_total_debt + initial_debt
            
            update_data = {
                "total_debt": new_total_debt,
                "phone_number": phone if phone != "N/A" else cust_record.get("phone_number"),
                "address": addr if addr != "N/A" else cust_record.get("address")
            }
            res = supabase.table("customers").update(update_data).eq("id", c_id).execute()
        else:
            # Kama hayupo, msajili mpya pamoja na deni lake la awali
            cust_dict = {
                "full_name": clean_name,
                "phone_number": phone,
                "address": addr,
                "total_debt": initial_debt
            }
            res = supabase.table("customers").insert(cust_dict).execute()

        return {"status": "success", "message": f"Mteja {clean_name} amesajiliwa na deni lake limewekwa mafanikio!", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/customers")
def get_customers():
    if not supabase:
        return {"status": "success", "data": []}
    try:
        supabase.table("customers").delete().lte("total_debt", 0).execute()

        cust_res = supabase.table("customers").select("*").execute()
        customers = cust_res.data if cust_res.data else []
        sales_res = supabase.table("bar_sales").select("customer_name, cashier").order("id", desc=True).execute()
        sales = sales_res.data if sales_res.data else []

        customer_cashier_map = {}
        for s in sales:
            c_name = s.get("customer_name")
            if c_name and c_name not in customer_cashier_map:
                customer_cashier_map[c_name] = s.get("cashier", "Admin")

        pending_res = supabase.table("debt_payments").select("*").eq("status", "Pending").execute()
        pending_payments = {p.get("customer_name"): p.get("amount_paid") for p in pending_res.data} if pending_res.data else {}

        result = []
        for c in customers:
            name = c.get("full_name")
            debt_val = c.get("total_debt", 0) or 0
            if debt_val <= 0:
                continue
            
            assigned_cashier = customer_cashier_map.get(name, "Admin")
            has_pending = name in pending_payments
            pending_amt = pending_payments.get(name, 0)

            result.append({
                "id": c.get("id"),
                "full_name": name,
                "phone_number": c.get("phone_number"),
                "address": c.get("address"),
                "total_debt": debt_val,
                "cashier": assigned_cashier,
                "has_pending": has_pending,
                "pending_amount": pending_amt
            })
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/customers/pay-debt")
def pay_debt(req: DebtPaymentRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        clean_cname = format_proper_case(req.customer_name)
        existing = supabase.table("debt_payments").select("*").ilike("customer_name", clean_cname).eq("status", "Pending").execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Mteja huyu tayari ana ombi la malipo linalosubiri idhini!")

        pay_data = {
            "customer_name": clean_cname,
            "cashier": req.cashier,
            "amount_paid": req.amount_paid,
            "status": "Pending"
        }
        res = supabase.table("debt_payments").insert(pay_data).execute()
        return {"status": "success", "message": "Ombi la malipo ya deni limetumwa! Linasubiri idhini ya Admin.", "data": res.data}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/admin/pending-payments")
def get_pending_payments():
    if not supabase:
        return {"status": "success", "data": []}
    try:
        res = supabase.table("debt_payments").select("*").eq("status", "Pending").execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/admin/approve-payment")
def approve_debt_payment(payload: dict):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    payment_id = payload.get("id")
    try:
        p_res = supabase.table("debt_payments").select("*").eq("id", int(payment_id)).execute()
        if not p_res.data:
            raise HTTPException(status_code=404, detail="Malipo hayajapatikana!")
        payment = p_res.data[0]
        if payment.get("status") == "Approved":
            raise HTTPException(status_code=400, detail="Malipo haya tayari yameshaidhinishwa!")

        cust_name = payment.get("customer_name")
        amount = payment.get("amount_paid")
        cashier = payment.get("cashier")

        supabase.table("debt_payments").update({"status": "Approved"}).eq("id", int(payment_id)).execute()

        c_res = supabase.table("customers").select("*").ilike("full_name", cust_name).execute()
        if c_res.data:
            cust = c_res.data[0]
            current_debt = cust.get("total_debt", 0) or 0
            new_debt = max(0.0, current_debt - amount)
            
            if new_debt == 0:
                supabase.table("customers").delete().eq("id", cust["id"]).execute()
            else:
                supabase.table("customers").update({"total_debt": new_debt}).eq("id", cust["id"]).execute()

        txn_id_val = f"TXN-{int(time.time())}"
        supabase.table("transactions").insert({
            "txn_id": txn_id_val,
            "txn_type": "Debt Repayment",
            "transaction_type": "Debt Repayment",
            "amount": amount,
            "description": f"Malipo ya deni la mteja {cust_name} yameidhinishwa",
            "recorded_by": cashier
        }).execute()

        return {"status": "success", "message": f"Malipo ya TZS {amount:,.2f} ya mteja {cust_name} yameidhinishwa kikamilifu!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/loans/calculate")
def calculate_reducing_balance(loan: LoanCalculationRequest):
    try:
        p = loan.principal
        monthly_rate = (loan.annual_rate / 100) / 12
        n = loan.months
        if monthly_rate > 0:
            monthly_payment = p * (monthly_rate * (1 + monthly_rate)**n) / (((1 + monthly_rate)**n) - 1)
        else:
            monthly_payment = p / n
        schedule = []
        balance = p
        total_interest = 0
        for month in range(1, n + 1):
            interest_payment = balance * monthly_rate
            principal_payment = monthly_payment - interest_payment
            balance -= principal_payment
            total_interest += interest_payment
            schedule.append({
                "month": month,
                "monthly_payment": round(monthly_payment, 2),
                "principal_repayment": round(principal_payment, 2),
                "interest_payment": round(interest_payment, 2),
                "remaining_balance": max(0, round(balance, 2))
            })
        return {
            "principal": p,
            "annual_interest_rate": f"{loan.annual_rate}%",
            "months": n,
            "monthly_installment": round(monthly_payment, 2),
            "total_interest": round(total_interest, 2),
            "total_payable": round(p + total_interest, 2),
            "repayment_schedule": schedule
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/loans/issue")
def issue_loan(loan: LoanCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database haipatikani!")
    try:
        p = loan.principal
        monthly_rate = (loan.annual_rate / 100) / 12
        n = loan.months
        if monthly_rate > 0:
            monthly_payment = p * (monthly_rate * (1 + monthly_rate)**n) / (((1 + monthly_rate)**n) - 1)
        else:
            monthly_payment = p / n
        total_payable = monthly_payment * n
        loan_data = {
            "customer_name": format_proper_case(loan.customer_name),
            "principal": p,
            "annual_rate": loan.annual_rate,
            "months": n,
            "total_payable": round(total_payable, 2),
            "remaining_balance": round(total_payable, 2),
            "status": "Active"
        }
        res = supabase.table("loans").insert(loan_data).execute()
        return {"status": "success", "message": "Mkopo umetolewa rasmi!", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/loans")
def get_loans():
    if not supabase:
        return {"status": "success", "data": []}
    try:
        res = supabase.table("loans").select("*").execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/transactions")
def get_transactions():
    if not supabase:
        return {"status": "success", "data": []}
    try:
        res = supabase.table("transactions").select("*").execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def home_ui():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>Faili la index.html halionekani!</h3>"
from google.genai import types
 
 
get_product_return_data_schema = types.FunctionDeclaration(
    name="get_product_return_data",
    description=(
        "Fetches all raw return records for a given product, scoped to the "
        "authenticated seller. Use this when the user wants the full list or "
        "raw detail of returns for a specific product, rather than a summary "
        "or breakdown."
    ),
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "The MongoDB ObjectId of the product as a 24-character hex string."
            }
        },
        "required": ["product_id"]
    }
)
 
get_return_reasons_breakdown_schema = types.FunctionDeclaration(
    name="get_return_reasons_breakdown",
    description=(
        "Retrieves a categorized breakdown of return reasons (e.g. Size Issue, "
        "Damaged, Not as Described, Wrong Item, Quality Issue, Other) for a "
        "specific product, with counts per category. Use this when the user "
        "asks WHY a product is being returned, what the main return reasons "
        "are, or wants a reason-level summary."
    ),
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "The MongoDB ObjectId of the product as a 24-character hex string."
            }
        },
        "required": ["product_id"]
    }
)
 
get_customer_feedback_schema = types.FunctionDeclaration(
    name="get_customer_feedback",
    description=(
        "Fetches customer reviews, star ratings, and free-text feedback "
        "comments for a specific product. Use this when the user asks about "
        "customer sentiment, ratings, reviews, or wants qualitative context "
        "behind why a product might be underperforming."
    ),
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "The MongoDB ObjectId of the product as a 24-character hex string."
            }
        },
        "required": ["product_id"]
    }
)
 
get_return_trend_schema = types.FunctionDeclaration(
    name="get_return_trend",
    description=(
        "Retrieves time-stamped return data grouped by month, showing how "
        "return volume and return reasons have changed over time for a "
        "specific product. Use this when the user asks about trends, whether "
        "returns are increasing or decreasing, or wants a timeline view. "
        "Only call this when time-series / historical analysis is relevant — "
        "not for a simple current-state summary."
    ),
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "The MongoDB ObjectId of the product as a 24-character hex string."
            }
        },
        "required": ["product_id"]
    }
)
 
get_order_delivery_data_schema = types.FunctionDeclaration(
    name="get_order_delivery_data",
    description=(
        "Fetches order and delivery timing data (order date, delivery date, "
        "delivery duration in days, fulfilment status) for a specific product. "
        "Use this when the user asks whether shipping delays, slow delivery, "
        "or fulfilment issues might be correlated with returns."
    ),
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "The MongoDB ObjectId of the product as a 24-character hex string."
            }
        },
        "required": ["product_id"]
    }
)
 
compare_seller_products_schema = types.FunctionDeclaration(
    name="compare_seller_products",
    description=(
        "Retrieves return metrics (order count, return count, return rate) "
        "across ALL of the authenticated seller's products, sorted by return "
        "rate descending. Use this when the user asks to compare products, "
        "wants to know which products have the highest/lowest return rates, "
        "or asks for a store-wide overview rather than a single product."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
 
detect_anomalies_schema = types.FunctionDeclaration(
    name="detect_anomalies",
    description=(
        "Identifies unusual patterns in return data for a specific product, "
        "such as sudden weekly volume spikes or drops, or a single return "
        "reason being unusually concentrated (e.g. a bad manufacturing batch "
        "or a sizing chart error). Use this when the user asks if something "
        "unusual or unexpected is happening, or wants root-cause flags rather "
        "than raw numbers."
    ),
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "The MongoDB ObjectId of the product as a 24-character hex string."
            }
        },
        "required": ["product_id"]
    }
)
 
get_sku_return_breakdown_schema = types.FunctionDeclaration(
    name="get_sku_return_breakdown",
    description=(
        "Returns return counts grouped by SKU / variant (e.g. by size or "
        "color) for a specific product. Use this when the user asks whether "
        "a particular variant (a specific size, color, etc.) is driving "
        "returns more than others — i.e. a variant-level rather than "
        "product-level question. Only useful if the product has multiple "
        "SKU variants."
    ),
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "The MongoDB ObjectId of the product as a 24-character hex string."
            }
        },
        "required": ["product_id"]
    }
)
 
 
ALL_TOOL_SCHEMAS = [
    get_product_return_data_schema,
    get_return_reasons_breakdown_schema,
    get_customer_feedback_schema,
    get_return_trend_schema,
    get_order_delivery_data_schema,
    compare_seller_products_schema,
    detect_anomalies_schema,
    get_sku_return_breakdown_schema,
]
# DSPy Integration Guide

## 🎯 DSPy Integration Overview

This version adds DSPy (Declarative Self-improving Language Programs) support, providing more structured and reliable order parsing.

### ✨ DSPy advantages

1. **Structured reasoning**: Signatures define explicit input/output formats
2. **Enforced JSON output**: keeps response formats consistent
3. **Automatic optimization**: DSPy can optimize prompts automatically
4. **Modular design**: the parsing flow is split into independent modules
5. **Better error handling**: multi-layer validation

## 🔧 DSPy Architecture

### Core modules

```
DSPyOrderClient
├── OrderTypeClassifier    # Detects single vs. multiple orders
├── SingleOrderParser      # Single-order parsing
├── MultiOrderParser       # Multi-order parsing (up to 5)
└── OrderValidator         # Data validation
```

### Signature definitions

```python
class SingleOrderSignature(dspy.Signature):
    """Parse a single order and output JSON"""
    order_text = dspy.InputField(desc="Single order text")
    order_json = dspy.OutputField(desc="Structured JSON data")

class MultiOrderSignature(dspy.Signature):
    """Parse multiple orders and output JSON"""
    order_text = dspy.InputField(desc="Multi-order text")
    orders_json = dspy.OutputField(desc="Multi-order JSON data")
```

### JSON Schema validation

The system uses strict JSON Schema validation:

```json
{
  "order_type": "single",
  "sender_name": null,        // optional
  "sender_phone": null,       // optional
  "receiver_name": "required",
  "receiver_phone": "required",
  "items": [
    {"name": "product name", "quantity": 1}
  ],
  "shipping_date": null,      // optional
  "shipping_address": "required"
}
```

## ⚙️ Configuration

### 1. Environment variables

Add to your `.env` file:

```bash
# DSPy settings
DSPY_API_KEY=your_openai_api_key_here  # Can be the same as OPENAI_API_KEY
DSPY_MODEL=gpt-4-0125-preview
DSPY_MAX_RETRIES=3

# Choose the order parsing client type
ORDER_CLIENT_TYPE=dspy  # 'openai' or 'dspy'
```

### 2. Install dependencies

```bash
pip install dspy-ai==2.4.9 jsonschema==4.20.0
```

### 3. Switching clients

The system can switch seamlessly between the OpenAI and DSPy clients:

- Set `ORDER_CLIENT_TYPE=openai` to use the original OpenAI client
- Set `ORDER_CLIENT_TYPE=dspy` to use the new DSPy client

## 🧪 Testing DSPy

Run the test script to verify DSPy functionality:

```bash
python test_dspy.py
```

The tests cover:
- ✅ Single-order parsing
- ✅ Multi-order parsing (2-5 orders)
- ✅ Error handling
- ✅ JSON format validation

## 📊 Comparison

| Feature | OpenAI client | DSPy client |
|------|---------------|-------------|
| JSON format guarantee | Basic | Enforced |
| Error handling | Standard | Multi-layer validation |
| Modularity | Low | High |
| Extensibility | Medium | High |
| Automatic optimization | None | Supported |

## 🔄 Migration Guide

### Migrating from OpenAI to DSPy

1. **No changes to existing code**: both clients expose the same interface
2. **Gradual migration**: test DSPy first, then switch fully once it checks out
3. **Rollback support**: switch back to the OpenAI client at any time

### Steps

```bash
# 1. Install DSPy dependencies
pip install dspy-ai jsonschema

# 2. Update environment variables
echo "ORDER_CLIENT_TYPE=dspy" >> .env

# 3. Test
python test_dspy.py

# 4. Restart the app
python main.py
```

## 🛡️ Improved Error Handling

The DSPy client provides more thorough error handling:

1. **JSON format validation**: strict validation with JSONSchema
2. **Business-logic validation**: checks required fields, phone formats, etc.
3. **Retries**: automatically retries on parse failure (up to 3 times)
4. **Fallback strategy**: suggests entering orders one at a time when multi-order parsing fails

## 📈 Advanced

### Custom DSPy modules

You can add new DSPy modules:

```python
class CustomOrderSignature(dspy.Signature):
    """Custom order parsing logic"""
    order_text = dspy.InputField(desc="Order text")
    custom_output = dspy.OutputField(desc="Custom output format")

class CustomOrderParser(dspy.Module):
    def __init__(self):
        self.parse = dspy.ChainOfThought(CustomOrderSignature)
    
    def forward(self, order_text):
        return self.parse(order_text=order_text)
```

### Model fine-tuning support

DSPy supports model fine-tuning and optimization:

```python
# Training data can be added later for optimization
trainset = [...]
teleprompter = BootstrapFewShot(metric=validate_order)
compiled_parser = teleprompter.compile(parser, trainset=trainset)
```

## 🚨 Caveats

1. **API usage**: DSPy may make more API calls (retries, validation)
2. **Response latency**: multi-layer validation may slightly increase processing time
3. **Compatibility**: fully compatible with existing LINE Bot features

## 🔮 Roadmap

1. **Model optimization**: collect usage data to optimize the DSPy modules
2. **Local model support**: support local LLMs (e.g. Ollama)
3. **More validation rules**: finer-grained business-logic validation
4. **Performance monitoring**: add a DSPy performance monitoring dashboard

---

## 💡 Best Practices

1. **Test in development first**: test DSPy in a development environment before production
2. **Monitor API usage**: keep an eye on DSPy's API call count
3. **Keep OpenAI as a fallback**: you can switch back to the OpenAI client at any time
4. **Run tests regularly**: use `test_dspy.py` to verify functionality periodically

DSPy gives you a more stable, reliable order parsing experience!

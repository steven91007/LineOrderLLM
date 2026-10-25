# 📋 LINE Bot Order Processing System - To-Do List

## 🐛 Item Parsing Bug Fixes (focus of the current branch)

### High priority
- [ ] Test ItemParser across various product formats
  - [ ] Test the "18A禮盒 x2" format
  - [ ] Test the "16A蛋糕一個" format  
  - [ ] Test the "20A花束 2束" format
  - [ ] Test mixed products "18A禮盒 x1, 16A蛋糕 x3"
- [ ] Fix the number-code retention problem
  - [ ] Make sure codes like 18A, 16A, 20A aren't stripped
  - [ ] Handle special formats such as "18A特製禮盒(客製包裝)"
- [ ] Improve the fallback parsing logic
  - [ ] Improve Chinese numeral conversion (一、二、三...)
  - [ ] Handle the various ways quantities are expressed
- [ ] Verify the DSPy and fallback integration

### Medium priority  
- [ ] Add more test cases
  - [ ] Edge cases (empty strings, special characters)
  - [ ] Malformed input handling
  - [ ] Large product lists
- [ ] Improve error handling and logging
- [ ] Performance optimization assessment

## 🏠 Address Normalization

### Done ✅
- [x] Implement the DSPy AddressNormalizer module
- [x] Build the county/city upgrade mapping table
- [x] Implement hybrid processing (AI + rules)
- [x] Preserve address notes (parenthesized content)
- [x] Integrate into the DSPy client

### To improve
- [ ] More address format tests
- [ ] Handling addresses in remote areas
- [ ] Stronger address validation

## 🤖 DSPy System Integration

### Done ✅
- [x] Configure the DSPy framework
- [x] Implement the order classifier
- [x] Implement the single/multi-order parsers
- [x] Implement the validator
- [x] Tracing integration (MLflow removed on 2026-08-14, replaced by Langfuse)

### To do
- [ ] Optimize few-shot examples
- [ ] Tune model parameters
- [ ] Improve error handling
- [ ] Optimize the retry mechanism

## 🔧 System Stability and Testing

### Testing
- [ ] Build a complete unit test suite
  - [ ] ItemParser tests
  - [ ] AddressNormalizer tests  
  - [ ] Order parser tests
  - [ ] End-to-end integration tests
- [ ] Build performance benchmarks
- [ ] Error-case handling tests

### Monitoring and logging
- [ ] Improve the Langfuse tracing configuration
- [ ] Add detailed debug logging
- [ ] Implement a health-check endpoint
- [ ] Add monitoring metrics

## 📱 LINE Bot Features

### Core features
- [ ] Test the LINE Bot webhook integration
- [ ] Verify the order confirmation flow
- [ ] Test the multi-order processing flow
- [ ] Test the optional sender field

### User experience
- [ ] Improve error messages
- [ ] Add usage instructions and examples
- [ ] Implement order status lookup
- [ ] Add FAQ handling

## 🚀 Deployment and Operations

### Deployment prep
- [ ] Docker containerization
- [ ] Environment variable configuration check
- [ ] Database migration scripts (if needed)
- [ ] CI/CD pipeline setup

### Documentation
- [ ] Update API docs
- [ ] Write a deployment guide  
- [ ] Troubleshooting guide
- [ ] User manual

## 🔍 Code Quality

### Refactoring and optimization
- [ ] Assess code structure refactoring
- [ ] Performance bottleneck analysis
- [ ] Memory usage optimization
- [ ] Dependency updates

### Security
- [ ] API key security review
- [ ] Stronger input validation
- [ ] Filter sensitive info out of error messages
- [ ] Implement rate limiting

---

## 📝 How to Use

### How to use this list:
1. ✅ Completed items are checked off
2. 🔄 Prefix in-progress items with `[🔄]`
3. ❌ Prefix items that hit problems with `[❌]` and describe the problem after it
4. 📝 Add a note after items that need more information

### Priority levels:
- **High priority**: affects core functionality; handle immediately
- **Medium priority**: improves user experience; handle soon  
- **Low priority**: optimizations; handle when time allows

### Current branch focus:
🎯 **fix/item-parsing-bugs**: focused on fixing item-parsing bugs and improving the feature

---

*Last updated: 2025-08-01*
*Maintainer: Claude Code Assistant*

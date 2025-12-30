# 🤖 Floating AI Assistant Widget - Quick Reference Guide

## ✨ What's New?

Your **AMR Surveillance Dashboard** now features a **floating AI Assistant widget** in the bottom-right corner of every page. This gives you ChatGPT-like AI access that's always just one click away!

---

## 🎯 How to Use

### Opening the Chat
1. Look at the **bottom-right corner** of any dashboard page
2. Click the **purple 🤖 Chat button**
3. A modal dialog will slide up above the button

### Asking Questions
Type your question in the text input box and click **Send**

#### Example Questions:
- **Data Analysis**: "What's our overall resistance rate?"
- **Recommendations**: "What should we do about high resistance?"
- **Education**: "How does antibiotic resistance develop?"
- **Ghana Context**: "What's the AMR situation in Ghana?"
- **Specific Organisms**: "Tell me about MRSA patterns in our data"
- **Trends**: "Are resistance rates getting worse?"
- **Risk Assessment**: "What are our main public health risks?"

### Closing the Chat
Click the **❌ Close Chat** button at the bottom of the modal

---

## 🧠 AI Capabilities

### What the AI Can Do:
✅ Analyze your surveillance data patterns
✅ Identify resistance trends and anomalies
✅ Answer questions about organisms and antibiotics
✅ Provide evidence-based recommendations
✅ Explain AMR concepts and resistance mechanisms
✅ Assess public health risks
✅ Connect findings to Ghana context and global AMR trends
✅ Reason beyond just your data (using domain knowledge)

### How It Works:
1. **First, it uses your data** - Analyzes everything in the database
2. **Then, it reasons with knowledge** - Uses expert domain knowledge
3. **Advanced mode (ChatGPT)** - Uses OpenAI GPT-3.5-turbo if available
4. **Fallback mode** - Uses intelligent local reasoning if OpenAI unavailable

---

## 🎨 Visual Design

### The Chat Button:
- **Location**: Bottom-right corner of screen
- **Color**: Purple-to-pink gradient
- **Shape**: Circular (60x60px)
- **Hover Effect**: Grows slightly larger

### The Chat Modal:
- **Size**: 400px wide × 600px tall (400×100% on mobile)
- **Position**: Slides up above the button
- **Header**: Purple gradient with "🤖 AMR AI Assistant" label
- **Messages**: Clean, easy-to-read format
- **Input**: Text box to type your messages
- **Responsive**: Full-screen on phones, floating window on desktop

---

## 🚀 Pro Tips

### Get Better Answers:
1. **Be specific** - "What resistance pattern in E. coli in Accra region?" (vs. "Tell me about resistance")
2. **Ask follow-ups** - "Why is that?" or "What should we do about it?"
3. **Provide context** - "Last quarter we had..." helps AI understand changes
4. **Mix topics** - Ask data questions then request recommendations

### Keyboard Shortcuts:
- **Type and press Enter** - Sends your message
- **Click Send button** - Alternative way to send
- **Click Close Chat** - Dismisses the modal

### Common Queries That Work Well:
```
"Summarize our resistance data"
"Which organisms are most dangerous?"
"What antibiotics are still effective?"
"How do we prevent spread of resistance?"
"Is MRSA a problem in our data?"
"What empirical therapy do you recommend?"
"Explain how genes transfer resistance"
```

---

## ⚙️ Technical Details

### Backend:
- **AI Module**: `src/ai_assistant.py` (EnhancedAIAssistant class)
- **API Key**: Embedded in code (ChatGPT-3.5-turbo)
- **Fallback**: Local rule-based reasoning if API unavailable
- **Data Access**: Reads from SQLite database in real-time

### Frontend:
- **Framework**: Streamlit
- **Widget Type**: Fixed position CSS modal
- **Styling**: Inline CSS with gradient and shadow effects
- **Responsiveness**: Mobile-friendly (100% width on small screens)

### Session Management:
- **Chat History**: Stored in session state (`st.session_state.ai_messages`)
- **Widget State**: Open/closed tracked in `st.session_state.ai_chat_open`
- **Persistence**: History clears when page refreshes (normal Streamlit behavior)

---

## 🔧 Troubleshooting

### Problem: Chat button not visible
**Solution**: 
- Scroll to bottom-right of page
- Try refreshing page (Ctrl+R)
- Check browser console for errors (F12)

### Problem: Chat won't respond
**Solution**:
- Check internet connection (for ChatGPT mode)
- Look for error message in chat
- App will automatically use fallback mode if ChatGPT unavailable
- Check that your question is clear and specific

### Problem: Responses seem generic
**Solution**:
- App is in fallback mode (local reasoning)
- Make sure OpenAI API is working (check response for "🤔 Using local knowledge")
- Try again - sometimes API timeouts occur
- Ask more specific questions about your actual data

### Problem: Chat disappeared
**Solution**:
- Click the 🤖 Chat button again to reopen it
- Refreshing the page resets the chat
- This is normal Streamlit behavior (sessions reset on refresh)

---

## 📊 Example Conversations

### Scenario 1: Data Analysis
```
User: "What's our overall resistance rate?"
Assistant: [Analyzes all_ast table, calculates percentages]
"Your overall resistance to first-line drugs is 38% across..."

User: "Which organisms are most resistant?"
Assistant: [Analyzes by organism type]
"Klebsiella pneumoniae (45%), Acinetobacter (42%)..."

User: "What should we do?"
Assistant: [Provides recommendations based on public health guidelines]
"Consider enhanced surveillance for K. pneumoniae, implement..."
```

### Scenario 2: Educational
```
User: "How does antibiotic resistance develop?"
Assistant: [Draws from domain knowledge database]
"Resistance develops through several mechanisms:
1. Genetic mutations...
2. Horizontal gene transfer...
3. Selection pressure from overuse..."

User: "Can this be prevented?"
Assistant: "Yes! Key strategies include:
- Antibiotic stewardship...
- Infection prevention...
- Vaccination programs..."
```

### Scenario 3: Risk Assessment
```
User: "What are our main public health risks?"
Assistant: [Analyzes resistance patterns and regional data]
"Top risks in your data:
1. High MRSA in urban regions (40% prevalence)
2. Emerging carbapenem resistance in Enterobacteriaceae...
3. Limited alternatives for severe infections..."

User: "Which region needs immediate attention?"
Assistant: [Geographic analysis]
"Greater Accra region shows highest risk with 2 high-risk organisms..."
```

---

## 🔐 Privacy & Security

✅ **All conversations are local** - No data sent to external servers except OpenAI
✅ **Your data is protected** - SQLite database never shared
✅ **API key is secure** - Embedded in backend, never exposed to frontend
✅ **No tracking** - No analytics or user tracking

---

## 📞 Support

If the floating widget isn't working:

1. **Check Streamlit console** (terminal) for error messages
2. **Verify all dependencies installed**: `pip install -r requirements.txt`
3. **Restart the app**: Stop and run `streamlit run app.py` again
4. **Check Python version**: Should be 3.8+ (tested on 3.14.2)

---

## 🎓 Learning Resources

Want to understand AMR better? Ask the AI Assistant!

**Recommended questions for new users:**
- "What is antibiotic resistance?"
- "Why is AMR a public health threat?"
- "How do bacteria become resistant?"
- "What can I do to prevent resistance?"
- "What is the difference between MRSA and ESBL?"
- "How does surveillance help prevent resistance?"
- "What's happening with AMR in Ghana?"

---

## Version Info

- **Widget Version**: 1.0 (Floating Modal)
- **AI Backend**: OpenAI GPT-3.5-turbo + Local Fallback
- **Release Date**: 2024
- **Status**: ✅ Production Ready

---

**Questions? Check the AI Assistant! It's powered by the same technology that makes ChatGPT amazing.** 🚀

// Simple WebSocket chat fix
console.log('Chat fix loaded');

// Override the sendMessage function with a working version
function sendMessage() {
    const input = document.getElementById('chat-input');
    const app = window.app;
    
    if (!input || !app) {
        console.log('Input or app not found');
        return;
    }
    
    const text = input.value.trim();
    if (!text) {
        console.log('Empty message, ignoring');
        return;
    }

    console.log('Sending message:', text);

    // Add message to UI first
    if (app.addMessage) {
        const messageData = { 
            text: text, 
            category: 'general',
            timestamp: new Date().toISOString()
        };
        console.log('Adding message to UI:', messageData);
        app.addMessage(messageData, true);
    }
    
    // Clear input
    input.value = '';

    // Send via WebSocket
    if (app.socket && app.currentUser) {
        const messagePayload = {
            username: app.currentUser.username,
            message: text,
            category: 'general',
            user_id: app.currentUser.username,
            timestamp: new Date().toISOString()
        };
        console.log('Socket and user available, sending WebSocket message with payload:', messagePayload);
        app.socket.emit('user_message', messagePayload);
        console.log('WebSocket message sent');
    } else {
        console.log('Socket or user not available:', {socket: !!app.socket, user: !!app.currentUser});
    }
    
    // Save chat history
    if (app.saveChatHistory) {
        console.log('Saving chat history');
        app.saveChatHistory();
    }
    
    console.log('Message sending process completed');
}

// Override the sendQuickMessage function too
function sendQuickMessage(text) {
    const input = document.getElementById('chat-input');
    if (input) {
        input.value = text;
        sendMessage();
    }
}

console.log('Chat fix functions overridden');
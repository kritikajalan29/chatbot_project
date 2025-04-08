// Add event listener for Enter key - initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('user-input').addEventListener('keypress', function(event) {
        if (event.key === 'Enter') {
            sendMessage();
        }
    });
    
    document.getElementById('artist-input').addEventListener('keypress', function(event) {
        if (event.key === 'Enter') {
            searchArtist();
        }
    });
});

// Keep track of the search state
let lastSearchedArtist = '';
let checkingResults = false;
let searchAttempts = 0;
const MAX_SEARCH_ATTEMPTS = 30; // Maximum number of attempts (30 seconds)

function updateDebugInfo(message) {
    const debugInfo = document.getElementById('debug-info');
    debugInfo.textContent = message;
    debugInfo.style.display = 'block';
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        debugInfo.style.display = 'none';
    }, 5000);
}

function updateSearchingStatus(message) {
    // Find the searching indicator message
    const searchingIndicator = document.getElementById('searching-indicator');
    if (searchingIndicator) {
        searchingIndicator.innerHTML = `<strong>Bot:</strong> <em>${message}</em>`;
    }
}

function checkArtistResults() {
    if (!lastSearchedArtist || checkingResults === false) return;
    
    // Increment search attempts
    searchAttempts++;
    
    // Update status message
    updateSearchingStatus(`Searching for artist details... (Attempt ${searchAttempts}/${MAX_SEARCH_ATTEMPTS})`);
    
    // If we reached max attempts, stop searching
    if (searchAttempts >= MAX_SEARCH_ATTEMPTS) {
        checkingResults = false;
        updateDebugInfo(`Stopped checking after ${MAX_SEARCH_ATTEMPTS} attempts`);
        
        // Update the message
        const searchingIndicator = document.getElementById('searching-indicator');
        if (searchingIndicator) {
            searchingIndicator.innerHTML = `<strong>Bot:</strong> <span style="color: orange;">Search timed out after 30 seconds. Please try again.</span>`;
        }
        return;
    }
    
    // Important: Update URL to use relative path instead of hardcoded localhost
    fetch(`/get-artist-results?artist_name=${encodeURIComponent(lastSearchedArtist)}`)
        .then(response => response.json())
        .then(data => {
            let chatBox = document.getElementById('chat-box');
            updateDebugInfo(`Received status: ${data.status}`);
            
            if (data.status === 'success') {
                // Remove searching indicator if it exists
                if (document.getElementById('searching-indicator')) {
                    document.getElementById('searching-indicator').remove();
                }
                
                // Format albums as list if available
                let albumsHtml = '';
                if (data.albums && data.albums.length > 0) {
                    albumsHtml = '<div class="album-list">';
                    data.albums.forEach(album => {
                        albumsHtml += `<div class="album-item">• ${album.title} (${album.track_count} tracks)</div>`;
                    });
                    albumsHtml += '</div>';
                }
                
                // Add artist details
                chatBox.innerHTML += `
                    <p><strong>Bot:</strong> Found artist: <strong>${data.name}</strong><br>
                    Total tracks: ${data.total_tracks}<br>
                    Albums: ${data.albums ? data.albums.length : 0}
                    ${albumsHtml}
                    </p>
                `;
                
                // Stop checking
                checkingResults = false;
                
                // Scroll to the bottom
                chatBox.scrollTop = chatBox.scrollHeight;
            } else if (data.status === 'pending') {
                // Keep checking every second
                setTimeout(checkArtistResults, 1000);
            } else if (data.status === 'not_found') {
                // Remove searching indicator if it exists
                if (document.getElementById('searching-indicator')) {
                    document.getElementById('searching-indicator').remove();
                }
                
                chatBox.innerHTML += `<p><strong>Bot:</strong> <span style="color: orange;">Sorry, I couldn't find any artist matching '${lastSearchedArtist}'.</span></p>`;
                
                // Stop checking
                checkingResults = false;
                
                // Scroll to the bottom
                chatBox.scrollTop = chatBox.scrollHeight;
            } else if (data.status === 'error') {
                // Remove searching indicator if it exists
                if (document.getElementById('searching-indicator')) {
                    document.getElementById('searching-indicator').remove();
                }
                
                chatBox.innerHTML += `<p><strong>Bot:</strong> <span style="color: red;">Error: ${data.message || "Unknown error occurred"}</span></p>`;
                
                // Stop checking
                checkingResults = false;
                
                // Scroll to the bottom
                chatBox.scrollTop = chatBox.scrollHeight;
            }
        })
        .catch(error => {
            console.error('Error checking results:', error);
            updateDebugInfo(`Error: ${error.message}`);
            // Keep checking if we get an error (server might not be ready yet)
            setTimeout(checkArtistResults, 2000);
        });
}

function searchArtist() {
    const artistName = document.getElementById('artist-input').value.trim();
    if (!artistName) return;
    
    // Reset search state - store in lowercase for consistent lookup
    lastSearchedArtist = artistName.toLowerCase();
    checkingResults = true;
    searchAttempts = 0;
    
    let chatBox = document.getElementById('chat-box');
    chatBox.innerHTML += `<p><strong>You:</strong> Searching for artist: ${artistName}</p>`;
    
    // Show searching indicator
    let searchingIndicator = document.createElement('p');
    searchingIndicator.id = 'searching-indicator';
    searchingIndicator.innerHTML = '<strong>Bot:</strong> <em>Searching for artist details...</em>';
    searchingIndicator.classList.add('progress-indicator');
    chatBox.appendChild(searchingIndicator);
    
    // Scroll to the bottom
    chatBox.scrollTop = chatBox.scrollHeight;
    
    // Update URL to use relative path instead of hardcoded localhost
    fetch('/trigger-artist', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ artist_name: artistName })
    })
    .then(response => response.json())
    .then(data => {
        updateDebugInfo(`Triggered search: ${data.status}`);
        
        // Start checking for results
        setTimeout(checkArtistResults, 1000);
        
        // Clear input
        document.getElementById('artist-input').value = '';
    })
    .catch(error => {
        // Remove searching indicator
        if (document.getElementById('searching-indicator')) {
            document.getElementById('searching-indicator').remove();
        }
        
        console.error('Error:', error);
        updateDebugInfo(`Error triggering search: ${error.message}`);
        chatBox.innerHTML += `<p><strong>Bot:</strong> <span style="color: red;">Error triggering artist search: ${error.message}</span></p>`;
        
        // Scroll to the bottom
        chatBox.scrollTop = chatBox.scrollHeight;
    });
}

function sendMessage() {
    var userInput = document.getElementById('user-input').value;
    if (userInput.trim() !== "") {
        let chatBox = document.getElementById('chat-box');
        chatBox.innerHTML += `<p><strong>You:</strong> ${userInput}</p>`;
        document.getElementById('user-input').value = "";
        
        // Add a "typing" indicator
        let typingIndicator = document.createElement('p');
        typingIndicator.id = 'typing-indicator';
        typingIndicator.innerHTML = '<strong>Bot:</strong> <em>Thinking...</em>';
        typingIndicator.classList.add('progress-indicator');
        chatBox.appendChild(typingIndicator);
        
        // Scroll to the bottom
        chatBox.scrollTop = chatBox.scrollHeight;
        
        // Update URL to use relative path instead of hardcoded localhost
        fetch('/message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: userInput })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok: ' + response.status);
            }
            return response.json();
        })
        .then(data => {
            // Remove typing indicator
            document.getElementById('typing-indicator').remove();
            
            // Add the bot's response
            chatBox.innerHTML += `<p><strong>Bot:</strong> ${data.response.replace(/\n/g, '<br>')}</p>`;
            
            // Scroll to the bottom
            chatBox.scrollTop = chatBox.scrollHeight;
        })
        .catch(error => {
            console.error('Error:', error);
            updateDebugInfo(`Error sending message: ${error.message}`);
            
            // Remove typing indicator
            if (document.getElementById('typing-indicator')) {
                document.getElementById('typing-indicator').remove();
            }
            
            // Show error message
            chatBox.innerHTML += `<p><strong>Bot:</strong> <span style="color: red;">Sorry, there was an error connecting to the server: ${error.message}</span></p>`;
            
            // Scroll to the bottom
            chatBox.scrollTop = chatBox.scrollHeight;
        });
    }
}

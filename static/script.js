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
    if (artistName === '') {
        alert('Please enter an artist name');
        return;
    }

    // Clear previous results
    document.getElementById('artist-results').innerHTML = '<div class="loading">Searching for artist...</div>';
    
    // Show the results area
    document.getElementById('artist-results-section').style.display = 'block';

    // Call the trigger artist endpoint
    fetch('/trigger-artist', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ artist_name: artistName }),
    })
    .then(response => response.json())
    .then(data => {
        console.log('Artist search response:', data);
        
        if (data.status === 'error') {
            // If there was an error, display it immediately
            document.getElementById('artist-results').innerHTML = `
                <div class="error">
                    <p>${data.message || 'Error searching for artist'}</p>
                </div>
            `;
            return;
        }
        
        // If we got immediate results, display them
        if (data.response) {
            document.getElementById('artist-results').innerHTML = `
                <div class="result">
                    <p>${formatMarkdown(data.response)}</p>
                </div>
            `;
            
            // If the response indicates we need to poll for results, start polling
            if (data.response.includes("I'm looking up information") || 
                data.response.includes("Please check back")) {
                pollForArtistResults(artistName);
            }
            return;
        }
        
        // If we don't have an immediate result, start polling
        pollForArtistResults(artistName);
    })
    .catch(error => {
        console.error('Error searching for artist:', error);
        document.getElementById('artist-results').innerHTML = `
            <div class="error">
                <p>Error connecting to the server. Please try again later.</p>
            </div>
        `;
    });
}

function pollForArtistResults(artistName, attempts = 0) {
    // Maximum number of polling attempts (30 * 2 seconds = 60 seconds total)
    const MAX_ATTEMPTS = 30;
    
    if (attempts >= MAX_ATTEMPTS) {
        document.getElementById('artist-results').innerHTML = `
            <div class="error">
                <p>It's taking longer than expected to find information about "${artistName}". 
                Please try again later.</p>
            </div>
        `;
        return;
    }
    
    // Update the loading message to show we're still working
    const loadingDiv = document.querySelector('#artist-results .loading');
    if (loadingDiv) {
        loadingDiv.innerHTML = `Searching for artist${'.'.repeat((attempts % 3) + 1)}`;
    }
    
    // Wait 2 seconds between polls
    setTimeout(() => {
        fetch(`/get-artist-results?artist_name=${encodeURIComponent(artistName)}`)
        .then(response => response.json())
        .then(data => {
            console.log('Poll response:', data);
            
            if (data.status === 'pending') {
                // Still processing, continue polling
                pollForArtistResults(artistName, attempts + 1);
                return;
            }
            
            if (data.status === 'error') {
                // Error occurred during processing
                document.getElementById('artist-results').innerHTML = `
                    <div class="error">
                        <p>${data.message || 'An error occurred while processing your request.'}</p>
                    </div>
                `;
                return;
            }
            
            if (data.status === 'not_found') {
                // Artist wasn't found
                document.getElementById('artist-results').innerHTML = `
                    <div class="result">
                        <p>No artist found matching "${artistName}".</p>
                    </div>
                `;
                return;
            }
            
            if (data.status === 'success') {
                // Success! Display the artist information
                const albums = data.albums || [];
                
                let resultHTML = `
                    <div class="result">
                        <h3>${data.name}</h3>
                        <p>Albums: ${albums.length}</p>
                        <p>Total Tracks: ${data.total_tracks || 0}</p>
                `;
                
                if (data.main_genres && data.main_genres.length > 0) {
                    resultHTML += `<p>Genres: ${data.main_genres.join(', ')}</p>`;
                }
                
                if (albums.length > 0) {
                    resultHTML += '<h4>Albums:</h4><ul>';
                    albums.forEach(album => {
                        resultHTML += `<li>${album.title} (${album.track_count} tracks)</li>`;
                    });
                    resultHTML += '</ul>';
                } else {
                    resultHTML += '<p>No albums found for this artist.</p>';
                }
                
                resultHTML += '</div>';
                document.getElementById('artist-results').innerHTML = resultHTML;
            }
        })
        .catch(error => {
            console.error('Error polling for results:', error);
            // Continue polling anyway in case it was a temporary network issue
            pollForArtistResults(artistName, attempts + 1);
        });
    }, 2000);
}

// Helper function to format markdown-style text to HTML
function formatMarkdown(text) {
    if (!text) return '';
    
    // Convert **bold** to <strong>bold</strong>
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Convert bullet points (• or *) to list items
    const hasBulletPoints = text.includes('• ') || /^\* /m.test(text);
    
    if (hasBulletPoints) {
        // Split into lines
        const lines = text.split('\n');
        let inList = false;
        let result = '';
        
        lines.forEach(line => {
            const trimmed = line.trim();
            
            // Check if this line is a bullet point
            if (trimmed.startsWith('• ') || trimmed.startsWith('* ')) {
                // Start a new list if we're not in one
                if (!inList) {
                    result += '<ul>';
                    inList = true;
                }
                
                // Add the list item
                result += `<li>${trimmed.substring(2)}</li>`;
            } else {
                // End the list if we're in one
                if (inList) {
                    result += '</ul>';
                    inList = false;
                }
                
                // Add the line
                result += line + '\n';
            }
        });
        
        // Close the list if we're still in one
        if (inList) {
            result += '</ul>';
        }
        
        text = result;
    }
    
    // Convert newlines to <br>
    text = text.replace(/\n/g, '<br>');
    
    return text;
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

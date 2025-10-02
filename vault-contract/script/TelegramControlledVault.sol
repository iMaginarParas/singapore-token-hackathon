// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title TelegramControlledVault
 * @dev Smart contract vault that executes actions approved via Telegram
 * 
 * SECURITY MODEL:
 * - User deposits funds into their personal vault
 * - Backend proposes actions (swap, withdraw, etc.)
 * - User approves via Telegram (yes/no)
 * - Backend executes approved action using signature verification
 */
contract TelegramControlledVault is ReentrancyGuard, Ownable {
    
    // ==================== STRUCTS ====================
    
    struct Action {
        uint256 actionId;
        address user;
        ActionType actionType;
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 minAmountOut;
        address recipient;
        bool executed;
        bool approved;
        uint256 timestamp;
        uint256 expiresAt;
    }
    
    enum ActionType {
        WITHDRAW,
        SWAP,
        REMOVE_LIQUIDITY,
        EMERGENCY_WITHDRAW
    }
    
    // ==================== STATE VARIABLES ====================
    
    mapping(address => mapping(address => uint256)) public userBalances; // user => token => balance
    mapping(uint256 => Action) public actions; // actionId => Action
    mapping(address => bool) public authorizedExecutors; // Backend addresses that can execute
    
    uint256 public nextActionId = 1;
    uint256 public constant ACTION_EXPIRY = 1 hours; // Actions expire after 1 hour
    
    // ==================== EVENTS ====================
    
    event Deposit(address indexed user, address indexed token, uint256 amount);
    event ActionProposed(uint256 indexed actionId, address indexed user, ActionType actionType);
    event ActionApproved(uint256 indexed actionId, address indexed user);
    event ActionExecuted(uint256 indexed actionId, address indexed user, bool success);
    event ActionExpired(uint256 indexed actionId);
    event EmergencyWithdraw(address indexed user, address indexed token, uint256 amount);
    
    // ==================== MODIFIERS ====================
    
    modifier onlyAuthorizedExecutor() {
        require(authorizedExecutors[msg.sender], "Not authorized executor");
        _;
    }
    
    // ==================== CONSTRUCTOR ====================
    
    constructor() {
        authorizedExecutors[msg.sender] = true; // Owner is authorized by default
    }
    
    // ==================== DEPOSIT FUNCTIONS ====================
    
    /**
     * @dev Deposit ERC20 tokens into vault
     */
    function deposit(address token, uint256 amount) external nonReentrant {
        require(amount > 0, "Amount must be > 0");
        
        IERC20(token).transferFrom(msg.sender, address(this), amount);
        userBalances[msg.sender][token] += amount;
        
        emit Deposit(msg.sender, token, amount);
    }
    
    /**
     * @dev Deposit native token (CELO) into vault
     */
    function depositNative() external payable nonReentrant {
        require(msg.value > 0, "Amount must be > 0");
        userBalances[msg.sender][address(0)] += msg.value;
        
        emit Deposit(msg.sender, address(0), msg.value);
    }
    
    // ==================== ACTION PROPOSAL ====================
    
    /**
     * @dev Backend proposes an action (called by authorized executor)
     */
    function proposeAction(
        address user,
        ActionType actionType,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minAmountOut,
        address recipient
    ) external onlyAuthorizedExecutor returns (uint256) {
        require(userBalances[user][tokenIn] >= amountIn, "Insufficient balance");
        
        uint256 actionId = nextActionId++;
        
        actions[actionId] = Action({
            actionId: actionId,
            user: user,
            actionType: actionType,
            tokenIn: tokenIn,
            tokenOut: tokenOut,
            amountIn: amountIn,
            minAmountOut: minAmountOut,
            recipient: recipient,
            executed: false,
            approved: false,
            timestamp: block.timestamp,
            expiresAt: block.timestamp + ACTION_EXPIRY
        });
        
        emit ActionProposed(actionId, user, actionType);
        return actionId;
    }
    
    // ==================== ACTION APPROVAL ====================
    
    /**
     * @dev User approves action (called by backend after Telegram yes/no)
     * Uses signature verification to ensure user actually approved
     */
    function approveAction(
        uint256 actionId,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external onlyAuthorizedExecutor {
        Action storage action = actions[actionId];
        require(!action.executed, "Already executed");
        require(block.timestamp <= action.expiresAt, "Action expired");
        
        // Verify signature
        bytes32 messageHash = getMessageHash(actionId, action.user);
        bytes32 ethSignedMessageHash = getEthSignedMessageHash(messageHash);
        address signer = ecrecover(ethSignedMessageHash, v, r, s);
        
        require(signer == action.user, "Invalid signature");
        
        action.approved = true;
        emit ActionApproved(actionId, action.user);
    }
    
    /**
     * @dev Simplified approval without signature (less secure, use with caution)
     */
    function approveActionDirect(uint256 actionId) external {
        Action storage action = actions[actionId];
        require(msg.sender == action.user, "Not action owner");
        require(!action.executed, "Already executed");
        require(block.timestamp <= action.expiresAt, "Action expired");
        
        action.approved = true;
        emit ActionApproved(actionId, action.user);
    }
    
    // ==================== ACTION EXECUTION ====================
    
    /**
     * @dev Execute approved action
     */
    function executeAction(uint256 actionId) external onlyAuthorizedExecutor nonReentrant {
        Action storage action = actions[actionId];
        require(action.approved, "Not approved");
        require(!action.executed, "Already executed");
        require(block.timestamp <= action.expiresAt, "Action expired");
        
        action.executed = true;
        
        bool success = false;
        
        if (action.actionType == ActionType.WITHDRAW) {
            success = _executeWithdraw(action);
        } else if (action.actionType == ActionType.SWAP) {
            success = _executeSwap(action);
        } else if (action.actionType == ActionType.REMOVE_LIQUIDITY) {
            success = _executeRemoveLiquidity(action);
        } else if (action.actionType == ActionType.EMERGENCY_WITHDRAW) {
            success = _executeEmergencyWithdraw(action);
        }
        
        emit ActionExecuted(actionId, action.user, success);
    }
    
    // ==================== INTERNAL EXECUTION LOGIC ====================
    
    function _executeWithdraw(Action storage action) internal returns (bool) {
        require(userBalances[action.user][action.tokenIn] >= action.amountIn, "Insufficient balance");
        
        userBalances[action.user][action.tokenIn] -= action.amountIn;
        
        if (action.tokenIn == address(0)) {
            // Native token
            (bool sent, ) = action.recipient.call{value: action.amountIn}("");
            require(sent, "Failed to send native token");
        } else {
            // ERC20 token
            IERC20(action.tokenIn).transfer(action.recipient, action.amountIn);
        }
        
        return true;
    }
    
    function _executeSwap(Action storage action) internal returns (bool) {
        // Implement swap logic with DEX (Ubeswap, etc.)
        // This is a placeholder - integrate with actual DEX router
        require(userBalances[action.user][action.tokenIn] >= action.amountIn, "Insufficient balance");
        
        userBalances[action.user][action.tokenIn] -= action.amountIn;
        
        // TODO: Call DEX router to swap
        // For now, just move tokens
        
        return true;
    }
    
    function _executeRemoveLiquidity(Action storage action) internal returns (bool) {
        // Implement liquidity removal logic
        require(userBalances[action.user][action.tokenIn] >= action.amountIn, "Insufficient balance");
        
        userBalances[action.user][action.tokenIn] -= action.amountIn;
        
        // TODO: Call DEX router to remove liquidity
        
        return true;
    }
    
    function _executeEmergencyWithdraw(Action storage action) internal returns (bool) {
        uint256 balance = userBalances[action.user][action.tokenIn];
        require(balance > 0, "No balance");
        
        userBalances[action.user][action.tokenIn] = 0;
        
        if (action.tokenIn == address(0)) {
            (bool sent, ) = action.user.call{value: balance}("");
            require(sent, "Failed to send");
        } else {
            IERC20(action.tokenIn).transfer(action.user, balance);
        }
        
        emit EmergencyWithdraw(action.user, action.tokenIn, balance);
        return true;
    }
    
    // ==================== SIGNATURE HELPERS ====================
    
    function getMessageHash(uint256 actionId, address user) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(actionId, user));
    }
    
    function getEthSignedMessageHash(bytes32 messageHash) public pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
    }
    
    // ==================== ADMIN FUNCTIONS ====================
    
    function addAuthorizedExecutor(address executor) external onlyOwner {
        authorizedExecutors[executor] = true;
    }
    
    function removeAuthorizedExecutor(address executor) external onlyOwner {
        authorizedExecutors[executor] = false;
    }
    
    // ==================== VIEW FUNCTIONS ====================
    
    function getUserBalance(address user, address token) external view returns (uint256) {
        return userBalances[user][token];
    }
    
    function getAction(uint256 actionId) external view returns (Action memory) {
        return actions[actionId];
    }
    
    function isActionExpired(uint256 actionId) external view returns (bool) {
        return block.timestamp > actions[actionId].expiresAt;
    }
}
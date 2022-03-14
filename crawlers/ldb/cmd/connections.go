package cmd

import (
	"database/sql"
	"fmt"
	"math/big"

	"github.com/bugout-dev/moonstream/crawlers/ldb/configs"

	"github.com/ethereum/go-ethereum/cmd/utils"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/rawdb"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/eth/ethconfig"
	"github.com/ethereum/go-ethereum/node"
	_ "github.com/lib/pq"
	"gopkg.in/urfave/cli.v1"
)

var (
	localConnections *LocalConnections
)

// Modified lightweight go-ethereum function
// Source: github.com/ethereum/go-ethereum/cmd/geth/config.go
func defaultNodeConfig() node.Config {
	cfg := node.DefaultConfig
	cfg.Name = "geth"
	return cfg
}

// Establish connection with blockchain
func setLocalChain(ctx *cli.Context) error {
	cfg := gethConfig{
		Eth:  ethconfig.Defaults,
		Node: defaultNodeConfig(),
	}

	// Apply flags
	utils.SetNodeConfig(ctx, &cfg.Node)
	stack, err := node.New(&cfg.Node)
	if err != nil {
		return fmt.Errorf("Failed to create the protocol stack: %v", err)
	}
	localConnections.Stack = stack

	utils.SetEthConfig(ctx, stack, &cfg.Eth)

	chain, chainDB := utils.MakeChain(ctx, stack)
	localConnections.Chain = chain
	localConnections.ChainDB = chainDB

	return nil
}

// Establish connection with database
func setDatabase() error {
	db, err := sql.Open("postgres", configs.MOONSTREAM_DB_URI)
	if err != nil {
		return fmt.Errorf("DSN parse error or another database initialization error: %v", err)
	}

	// Set the maximum number of concurrently idle connections,
	// by default sql.DB allows a maximum of 2 idle connections.
	db.SetMaxIdleConns(configs.MOONSTREAM_DB_MAX_IDLE_CONNS)

	// Set the maximum lifetime of a connection.
	// Longer lifetime increase memory usage.
	db.SetConnMaxLifetime(configs.MOONSTREAM_DB_CONN_MAX_LIFETIME)

	localConnections.Database = db

	return nil
}

// Retrive block from blockchain
func (lc *LocalConnections) getChainBlock(number uint64) (*types.Block, error) {
	block := lc.Chain.GetBlockByNumber(number)
	if block == nil {
		return nil, fmt.Errorf("Not found %d block in chain", number)
	}
	return block, nil
}

// Retrive block transactions from blockchain
func (lc *LocalConnections) getChainTxs(blockHash common.Hash, number uint64) []*types.Transaction {
	var transactions []*types.Transaction
	body := rawdb.ReadBody(lc.ChainDB, blockHash, number)
	for _, tx := range body.Transactions {
		transactions = append(transactions, tx)
	}

	return transactions
}

// Retrive block with transactions from database
func (lc *LocalConnections) getDatabaseBlockTxs(blockchain, blockHash string) (LightBlock, error) {
	var lBlock LightBlock
	var txs []LightTransaction
	query := fmt.Sprintf(
		`SELECT 
			%s_blocks.hash,
			%s_blocks.block_number,
			%s_transactions.hash
		FROM %s_blocks
			LEFT JOIN %s_transactions ON %s_blocks.block_number = %s_transactions.block_number
		WHERE %s_blocks.hash = '%s';`,
		blockchain, blockchain, blockchain, blockchain, blockchain, blockchain, blockchain, blockchain, blockHash,
	)
	rows, err := lc.Database.Query(query)
	if err != nil {
		return lBlock, fmt.Errorf("An error occurred during sql operation: %v", err)
	}
	defer rows.Close()

	for rows.Next() {
		var blockHash, blockNumberStr, txHash sql.NullString
		err := rows.Scan(&blockHash, &blockNumberStr, &txHash)
		if err != nil {
			return lBlock, fmt.Errorf("An error occurred during sql operation: %v", err)
		}

		var lTx LightTransaction
		if txHash.Valid != false {
			lTx = LightTransaction{
				Hash: txHash.String,
			}
			txs = append(lBlock.Transactions, lTx)
		}

		blockNumber := new(big.Int)
		blockNumber, ok := blockNumber.SetString(blockNumberStr.String, 10)
		if !ok {
			return lBlock, fmt.Errorf("Unable to parse block number")
		}

		lBlock = LightBlock{
			Hash:         blockHash.String,
			Number:       blockNumber,
			Transactions: txs,
		}
	}

	return lBlock, nil
}

func prepareBlockQuery(blockchain string, block *types.Block, td *big.Int) string {
	// block.extraData doesn't exist at Polygon mainnet
	var extraData interface{}
	if block.Extra() == nil {
		extraData = "NULL"
	} else {
		extraData = fmt.Sprintf("'0x%x'", block.Extra())
	}

	// For support of blocks before London hardfork
	var baseFee interface{}
	if block.BaseFee() == nil {
		baseFee = "NULL"
	} else {
		baseFee = block.BaseFee()
	}

	blockQuery := fmt.Sprintf(
		`INSERT INTO %s_blocks (
			block_number,
			difficulty,
			extra_data,
			gas_limit,
			gas_used,
			base_fee_per_gas,
			hash,
			logs_bloom,
			miner,
			nonce,
			parent_hash,
			receipt_root,
			uncles,
			size,
			state_root,
			timestamp,
			total_difficulty,
			transactions_root
		) VALUES (%d, %d, %v, %d, %d, %v, '%s', '0x%x', '%s', '0x%x', '0x%x', '0x%x', '0x%x', %f, '0x%x', %d, %d, '0x%x')`,
		blockchain,
		block.Number(),
		block.Difficulty(),
		extraData,
		block.GasLimit(),
		block.GasUsed(),
		baseFee,
		block.Hash(),
		block.Bloom(),
		block.Coinbase(),
		block.Nonce(),
		block.ParentHash(),
		block.ReceiptHash(),
		block.UncleHash(),
		block.Size(),
		block.Root(),
		block.Time(),
		td,
		block.TxHash(),
	)

	return blockQuery
}

func prepareTxsQuery(blockchain string, block *types.Block, txs []*types.Transaction, signer types.Signer) (string, error) {
	txsQuery := fmt.Sprintf(
		`INSERT INTO %s_transactions (
			hash,
			block_number,
			from_address,
			to_address,
			gas,
			gas_price,
			max_fee_per_gas,
			max_priority_fee_per_gas,
			input,
			nonce,
			transaction_index,
			transaction_type,
			value
		) VALUES `,
		blockchain,
	)

	for i, tx := range txs {
		var maxFeePerGas interface{}
		maxFeePerGas = "NULL"

		var maxPriorityFeePerGas interface{}
		maxPriorityFeePerGas = "NULL"

		m, err := tx.AsMessage(signer, block.Number())
		if err != nil {
			return "", fmt.Errorf("Transaction to message transformation failed: %v", err)
		}
		if i != 0 {
			txsQuery += ","
		}
		txsQuery += fmt.Sprintf(
			`('%s', %d, '%s', '%s', %d, %d, %v, %v, '0x%x', %d, %d, %d, %d)`,
			tx.Hash(),
			block.Number(),
			m.From(),
			tx.To(),
			tx.Gas(),
			tx.GasPrice(),
			maxFeePerGas,
			maxPriorityFeePerGas,
			tx.Data(),
			tx.Nonce(),
			i,
			tx.Type(),
			tx.Value(),
		)
	}

	return txsQuery, nil
}

// Write block with transactions to database
func (lc *LocalConnections) writeDatabaseBlockTxs(
	blockchain string, block *types.Block, txs []*types.Transaction, td *big.Int,
) error {
	dbTx, err := lc.Database.Begin()
	if err != nil {
		return fmt.Errorf("Unable to begin database transaction, err: %v", err)
	}

	blockQuery := prepareBlockQuery(blockchain, block, td)
	_, err = dbTx.Exec(blockQuery)
	if err != nil {
		dbTx.Rollback()
		return fmt.Errorf("An error occurred during sql operation: %v", err)
	}

	genesisHash := common.HexToHash("0xd4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3")
	chainConfig := rawdb.ReadChainConfig(lc.ChainDB, genesisHash)
	signer := types.MakeSigner(chainConfig, block.Number())

	if len(txs) > 0 {
		txsQuery, err := prepareTxsQuery(blockchain, block, txs, signer)
		if err != nil {
			dbTx.Rollback()
			return err
		}
		_, err = dbTx.Exec(txsQuery)
		if err != nil {
			dbTx.Rollback()
			return fmt.Errorf("An error occurred during sql operation: %v", err)
		}
	}

	err = dbTx.Commit()
	if err != nil {
		return fmt.Errorf("Unable to commit transactions: %v", err)
	}

	return nil
}
